"""Supabase persistence for ML — training_runs, embedding_vectors, ml_scores.

Security:
  • FastAPI writes via service-role pool after tenant principal checks.
  • Only metadata / scores / latents — never ciphertext or raw envelopes.
  • Features may be pulled from stream_results (cipher_len, scores) only.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings

logger = logging.getLogger("forjd.ml.store")


# --- Soft schema (dev); production applies sql/016 ---
async def ensure_ml_store_schema(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS training_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'completed',
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            artifact_path TEXT,
            family TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'fit',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        "ALTER TABLE training_runs ADD COLUMN IF NOT EXISTS family TEXT NOT NULL DEFAULT ''"
    )
    await pool.execute(
        "ALTER TABLE training_runs ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'fit'"
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS ml_scores (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            family TEXT NOT NULL,
            model_name TEXT NOT NULL DEFAULT '',
            score DOUBLE PRECISION,
            is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
            features JSONB NOT NULL DEFAULT '{}'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.8g}" for x in embedding) + "]"


# --- Feature pull from sealed-stream metadata (never ciphertext) ---
async def features_from_stream_results(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    limit: int = 128,
) -> list[list[float]]:
    """Build tabular features from stream_results for classical / ensemble fit."""
    rows = await pool.fetch(
        """
        SELECT score, is_anomaly, features, kind
        FROM stream_results
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        tenant_id,
        limit,
    )
    out: list[list[float]] = []
    for r in rows:
        feats = r["features"]
        if isinstance(feats, str):
            feats = json.loads(feats)
        feats = feats or {}
        cipher_len = float(feats.get("cipher_len") or feats.get("mean_cipher_len") or 0.0)
        z = float(feats.get("z_score") or feats.get("zscore") or 0.0)
        rate = float(feats.get("rate") or feats.get("events_per_min") or 0.0)
        score = float(r["score"] or 0.0)
        anom = 1.0 if r["is_anomaly"] else 0.0
        kind_digest = hashlib.sha256(str(r["kind"] or "").encode()).digest()
        kind_hash = int.from_bytes(kind_digest[:4], "big") / float(2**32)
        out.append([score, anom, cipher_len, z, rate, kind_hash])
    return out


async def series_from_stream_results(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    limit: int = 96,
) -> list[float]:
    """Latency-like series from stream_results.score for forecasting / seq models."""
    rows = await pool.fetch(
        """
        SELECT score
        FROM (
            SELECT score, created_at
            FROM stream_results
            WHERE tenant_id = $1::uuid AND score IS NOT NULL
            ORDER BY created_at DESC
            LIMIT $2
        ) recent
        ORDER BY created_at ASC
        """,
        tenant_id,
        limit,
    )
    series = [float(r["score"]) for r in rows]
    return [value for value in series if math.isfinite(value)]


# --- Training runs ---
async def record_training_run(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    family: str,
    model_name: str,
    metrics: dict[str, Any],
    artifact_path: str | None = None,
    status: str = "completed",
    model_version: str = "",
) -> str:
    await ensure_ml_store_schema(pool)
    row = await pool.fetchrow(
        """
        INSERT INTO training_runs (
            tenant_id, model_name, model_version, status,
            metrics, artifact_path, family, kind
        )
        VALUES (
            $1::uuid, $2, $3, $4,
            $5::jsonb, $6, $7, 'fit'
        )
        RETURNING id::text
        """,
        tenant_id,
        model_name,
        model_version or settings.ML_MODEL_VERSION,
        status,
        json.dumps(metrics),
        artifact_path,
        family,
    )
    return str(row["id"])


# --- pgvector latents ---
async def persist_embedding(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    embedding: list[float],
    reconstruction_error: float | None = None,
    is_anomaly: bool = False,
    series_id: str = "default",
    model_version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    await ensure_ml_store_schema(pool)
    # Prefer production embedding_vectors; fall back soft-create shape.
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_vectors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            telemetry_event_id UUID,
            series_id TEXT NOT NULL DEFAULT 'default',
            model_version TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            embedding vector(16),
            reconstruction_error DOUBLE PRECISION,
            is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
            context_ciphertext TEXT,
            context_nonce TEXT,
            context_key_id TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    # Truncate/pad to ML_LATENT_DIM for the fixed vector(16) column.
    dim = int(settings.ML_LATENT_DIM)
    vec = list(embedding[:dim])
    if len(vec) < dim:
        vec.extend([0.0] * (dim - len(vec)))
    row = await pool.fetchrow(
        """
        INSERT INTO embedding_vectors (
            tenant_id, series_id, model_version,
            embedding, reconstruction_error, is_anomaly, metadata
        )
        VALUES (
            $1::uuid, $2, $3,
            $4::vector, $5, $6, $7::jsonb
        )
        RETURNING id::text
        """,
        tenant_id,
        series_id,
        model_version or settings.ML_MODEL_VERSION,
        _vector_literal(vec),
        reconstruction_error,
        is_anomaly,
        json.dumps(metadata or {}),
    )
    return str(row["id"])


async def nearest_embeddings(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    embedding: list[float],
    limit: int = 5,
) -> list[dict[str, Any]]:
    dim = int(settings.ML_LATENT_DIM)
    vec = list(embedding[:dim])
    if len(vec) < dim:
        vec.extend([0.0] * (dim - len(vec)))
    rows = await pool.fetch(
        """
        SELECT id::text, series_id, model_version, reconstruction_error,
               is_anomaly, metadata, created_at,
               1 - (embedding <=> $2::vector) AS cosine_sim
        FROM embedding_vectors
        WHERE tenant_id = $1::uuid AND embedding IS NOT NULL
        ORDER BY embedding <=> $2::vector
        LIMIT $3
        """,
        tenant_id,
        _vector_literal(vec),
        limit,
    )
    out = []
    for r in rows:
        meta = r["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        out.append(
            {
                "id": r["id"],
                "series_id": r["series_id"],
                "model_version": r["model_version"],
                "reconstruction_error": r["reconstruction_error"],
                "is_anomaly": r["is_anomaly"],
                "cosine_sim": float(r["cosine_sim"] or 0.0),
                "metadata": meta,
                "created_at": r["created_at"].isoformat(),
            }
        )
    return out


# --- Score rows ---
async def persist_scores(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    family: str,
    rows: list[dict[str, Any]],
) -> int:
    await ensure_ml_store_schema(pool)
    n = 0
    for row in rows:
        await pool.execute(
            """
            INSERT INTO ml_scores (
                tenant_id, family, model_name, score, is_anomaly, features, metadata
            )
            VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb, $7::jsonb)
            """,
            tenant_id,
            family,
            str(row.get("model_name") or family),
            row.get("score"),
            bool(row.get("is_anomaly") or False),
            json.dumps(row.get("features") or {}),
            json.dumps(row.get("metadata") or {}),
        )
        n += 1
    return n


async def list_recent_training_runs(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Recent training_runs for partner self-benchmark dashboards."""
    rows = await pool.fetch(
        """
        SELECT id::text, family, model_name, model_version, status,
               metrics, artifact_path, created_at
        FROM training_runs
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        str(tenant_id),
        limit,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        metrics = r["metrics"]
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except json.JSONDecodeError:
                metrics = {}
        out.append(
            {
                "id": r["id"],
                "family": r["family"] or r["model_name"],
                "model_name": r["model_name"],
                "model_version": r["model_version"],
                "status": r["status"],
                "metrics": metrics if isinstance(metrics, dict) else {},
                "artifact_path": r["artifact_path"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
        )
    return out


def benchmark_from_training_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Shape training_runs into the Angular BenchmarkRollup contract."""
    completed = [
        row
        for row in runs
        if str(row.get("status") or "").lower() in {"completed", "success", "ok", ""}
    ]
    if not completed:
        return {
            "score_percent": None,
            "accuracy_percent": None,
            "mae": None,
            "rmse": None,
            "dataset_size": 0,
            "models_evaluated": 0,
            "measured_models": 0,
            "evaluation_status": "insufficient_data",
            "created_at": None,
        }

    scores: list[float] = []
    accuracies: list[float] = []
    maes: list[float] = []
    rmses: list[float] = []
    samples = 0
    families: set[str] = set()
    newest: str | None = None
    for row in completed:
        families.add(str(row.get("family") or row.get("model_name") or "model"))
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        for key in ("benchmark_score", "score", "ces_sla", "r2", "accuracy"):
            if metrics.get(key) is not None:
                try:
                    val = float(metrics[key])
                except (TypeError, ValueError):
                    continue
                # accuracy/r2 often 0–1; benchmark_score may be 0–100
                if key in {"accuracy", "r2"} and 0.0 <= val <= 1.0:
                    accuracies.append(val * 100.0)
                elif key == "benchmark_score" or (0.0 <= val <= 100.0):
                    scores.append(val if val > 1.0 or key == "benchmark_score" else val * 100.0)
                break
        if metrics.get("accuracy") is not None:
            with contextlib.suppress(TypeError, ValueError):
                acc = float(metrics["accuracy"])
                accuracies.append(acc * 100.0 if acc <= 1.0 else acc)
        if metrics.get("mae") is not None:
            with contextlib.suppress(TypeError, ValueError):
                maes.append(float(metrics["mae"]))
        if metrics.get("rmse") is not None:
            with contextlib.suppress(TypeError, ValueError):
                rmses.append(float(metrics["rmse"]))
        for key in ("n_samples", "dataset_size", "n_windows", "n_points"):
            if metrics.get(key) is not None:
                with contextlib.suppress(TypeError, ValueError):
                    samples += int(metrics[key])
                break
        if newest is None and row.get("created_at"):
            newest = str(row["created_at"])

    measured = len(families)
    score_percent = round(sum(scores) / len(scores), 2) if scores else None
    if score_percent is None and accuracies:
        score_percent = round(sum(accuracies) / len(accuracies), 2)
    # Derive a soft score from inverse RMSE when nothing else is available.
    if score_percent is None and rmses:
        avg_rmse = sum(rmses) / len(rmses)
        score_percent = round(max(0.0, min(100.0, 100.0 - avg_rmse * 10.0)), 2)

    return {
        "score_percent": score_percent,
        "accuracy_percent": round(sum(accuracies) / len(accuracies), 2) if accuracies else None,
        "mae": round(sum(maes) / len(maes), 6) if maes else None,
        "rmse": round(sum(rmses) / len(rmses), 6) if rmses else None,
        "dataset_size": samples,
        "models_evaluated": measured,
        "measured_models": measured if score_percent is not None else 0,
        "evaluation_status": "measured" if score_percent is not None else "insufficient_data",
        "created_at": newest,
    }


async def list_recent_scores(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    family: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if family:
        rows = await pool.fetch(
            """
            SELECT id::text, family, model_name, score, is_anomaly,
                   features, metadata, created_at
            FROM ml_scores
            WHERE tenant_id = $1::uuid AND family = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            str(tenant_id),
            family,
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id::text, family, model_name, score, is_anomaly,
                   features, metadata, created_at
            FROM ml_scores
            WHERE tenant_id = $1::uuid
            ORDER BY created_at DESC
            LIMIT $2
            """,
            str(tenant_id),
            limit,
        )
    out = []
    for r in rows:
        feats = r["features"]
        meta = r["metadata"]
        if isinstance(feats, str):
            feats = json.loads(feats)
        if isinstance(meta, str):
            meta = json.loads(meta)
        out.append(
            {
                "id": r["id"],
                "family": r["family"],
                "model_name": r["model_name"],
                "score": r["score"],
                "is_anomaly": r["is_anomaly"],
                "features": feats,
                "metadata": meta,
                "created_at": r["created_at"].isoformat(),
            }
        )
    return out


def empty_temporal_signal(*, status: str = "insufficient_data") -> dict[str, Any]:
    return {
        "spiking_temporal_forecast": None,
        "temporal_status": status,
        "temporal_backend": None,
        "temporal_sample_count": 0,
        "temporal_scored_at": None,
        "uses_norse": False,
    }


def temporal_signal_from_score(
    row: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Shape one persisted Norse score without consulting runtime packages."""
    if not row:
        return empty_temporal_signal()

    features = row.get("features") if isinstance(row.get("features"), dict) else {}
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    scored_at = row.get("created_at")
    scored_at_text = (
        scored_at.isoformat() if isinstance(scored_at, datetime) else str(scored_at or "") or None
    )

    def _invalid() -> dict[str, Any]:
        signal = empty_temporal_signal(status="error")
        signal["temporal_scored_at"] = scored_at_text
        return signal

    try:
        raw_score = float(row["score"])
    except (KeyError, TypeError, ValueError):
        return _invalid()
    if not math.isfinite(raw_score) or not 0.0 <= raw_score <= 1.0:
        return _invalid()

    backend = str(features.get("backend") or "").strip() or None
    if backend not in {"norse_lif", "gru_mlp_fallback"}:
        return _invalid()
    uses_norse = backend == "norse_lif"

    sample_value = features.get("sample_count", metadata.get("sample_count"))
    try:
        sample_count = max(0, int(sample_value or 0))
    except (TypeError, ValueError):
        return _invalid()
    if sample_count <= 0 or not scored_at:
        return _invalid()

    temporal_status = "ready"
    try:
        parsed = (
            scored_at
            if isinstance(scored_at, datetime)
            else datetime.fromisoformat(str(scored_at).replace("Z", "+00:00"))
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        reference = now or datetime.now(UTC)
        stale_after = timedelta(seconds=float(settings.TRAINING_REFRESH_SECONDS) * 2.0)
        if parsed - reference > timedelta(minutes=5):
            return _invalid()
        if reference - parsed > stale_after:
            temporal_status = "stale"
    except (TypeError, ValueError):
        return _invalid()

    return {
        "spiking_temporal_forecast": round(raw_score * 100.0, 2),
        "temporal_status": temporal_status,
        "temporal_backend": backend,
        "temporal_sample_count": sample_count,
        "temporal_scored_at": scored_at_text,
        "uses_norse": uses_norse,
    }


async def latest_temporal_signal(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
) -> dict[str, Any]:
    rows = await list_recent_scores(
        pool,
        tenant_id=tenant_id,
        family="norse_ssn",
        limit=1,
    )
    if rows:
        return temporal_signal_from_score(rows[0])

    run = await pool.fetchrow(
        """
        SELECT status, metrics
        FROM training_runs
        WHERE tenant_id = $1::uuid
          AND (family = 'norse_ssn' OR model_name = 'norse_ssn')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        str(tenant_id),
    )
    signal = empty_temporal_signal()
    if run is None or str(run["status"] or "").lower() != "insufficient_data":
        return signal
    metrics = run["metrics"]
    if isinstance(metrics, str):
        with contextlib.suppress(json.JSONDecodeError):
            metrics = json.loads(metrics)
    if not isinstance(metrics, dict):
        return signal
    with contextlib.suppress(TypeError, ValueError):
        signal["temporal_sample_count"] = max(0, int(metrics.get("sample_count") or 0))
    return signal
