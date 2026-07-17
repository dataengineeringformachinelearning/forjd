"""Unsupervised anomaly PoC — LSTM-AE + Supabase pgvector embeddings."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import numpy as np

from app.core.config import settings
from app.pipelines.anomaly import run_anomaly_flow
from app.services.ml import lstm_autoencoder as lae

logger = logging.getLogger("forjd.anomaly")

_lock = threading.Lock()
_model: Any | None = None
_loaded_version: str | None = None


def _checkpoint_path() -> Path:
    return Path(settings.ML_MODEL_DIR) / f"{settings.ML_MODEL_VERSION}.pt"


def ml_status() -> dict[str, Any]:
    path = _checkpoint_path()
    return {
        "ok": lae.torch_available(),
        "torch": lae.torch_available(),
        "model_version": settings.ML_MODEL_VERSION,
        "seq_len": settings.ML_SEQ_LEN,
        "latent_dim": settings.ML_LATENT_DIM,
        "threshold": settings.ML_ANOMALY_THRESHOLD,
        "checkpoint": str(path) if path.exists() else None,
        "loaded": _model is not None,
        "hint": None
        if lae.torch_available()
        else "Install with: uv sync --group ml",
    }


def _vector_literal(embedding: list[float]) -> str:
    """pgvector text form accepted by asyncpg as $1::vector."""
    return "[" + ",".join(f"{x:.8g}" for x in embedding) + "]"


async def ensure_anomaly_tables(pool: asyncpg.Pool) -> None:
    try:
        await pool.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except asyncpg.PostgresError as exc:
        # Supabase often requires enabling "vector" in the dashboard first.
        logger.warning("CREATE EXTENSION vector failed: %s", exc)
    await pool.execute(
        f"""
        CREATE TABLE IF NOT EXISTS anomaly_embeddings (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            series_id TEXT NOT NULL DEFAULT 'default',
            model_version TEXT NOT NULL,
            series_window JSONB NOT NULL DEFAULT '[]'::jsonb,
            embedding vector({int(settings.ML_LATENT_DIM)}) NOT NULL,
            reconstruction_error DOUBLE PRECISION NOT NULL,
            is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS anomaly_embeddings_created_at_idx
          ON anomaly_embeddings (created_at DESC)
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS anomaly_embeddings_series_id_idx
          ON anomaly_embeddings (series_id)
        """
    )
    # HNSW may already exist from sql/002; ignore duplicate errors.
    try:
        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS anomaly_embeddings_embedding_hnsw_idx
              ON anomaly_embeddings
              USING hnsw (embedding vector_cosine_ops)
            """
        )
    except asyncpg.PostgresError as exc:
        logger.info("hnsw index skipped: %s", exc)


def _collect_windows(
    *,
    values: list[float] | None,
    windows: list[list[float]] | None,
    use_synthetic: bool,
) -> np.ndarray:
    seq = settings.ML_SEQ_LEN
    parts: list[np.ndarray] = []

    if windows:
        parts.append(
            np.stack([lae.pad_or_truncate(w, seq) for w in windows], axis=0)
        )
    if values:
        parts.append(lae.windows_from_series(values, seq))
    if use_synthetic or not parts:
        parts.append(lae.synthetic_normal_windows(n_windows=128, seq_len=seq))

    return np.concatenate(parts, axis=0)


def _get_or_load_model() -> Any:
    global _model, _loaded_version
    with _lock:
        if _model is not None and _loaded_version == settings.ML_MODEL_VERSION:
            return _model
        path = _checkpoint_path()
        if not path.exists():
            raise RuntimeError(
                "No trained checkpoint — POST /api/v1/anomaly/fit first"
            )
        model, _meta = lae.load_checkpoint(
            path,
            hidden_dim=settings.ML_HIDDEN_DIM,
            latent_dim=settings.ML_LATENT_DIM,
        )
        _model = model
        _loaded_version = settings.ML_MODEL_VERSION
        return _model


def _set_model(model: Any) -> None:
    global _model, _loaded_version
    with _lock:
        _model = model
        _loaded_version = settings.ML_MODEL_VERSION


async def fit_anomaly(
    *,
    pool: asyncpg.Pool | None,
    series_id: str = "default",
    values: list[float] | None = None,
    windows: list[list[float]] | None = None,
    epochs: int | None = None,
    use_synthetic: bool = True,
) -> dict[str, Any]:
    layers: dict[str, Any] = {}

    if not lae.torch_available():
        return {
            "ok": False,
            "error": "PyTorch not installed — uv sync --group ml",
            "layers": {"torch": {"ok": False}},
            "model_version": settings.ML_MODEL_VERSION,
            "series_id": series_id,
        }

    train_epochs = epochs or settings.ML_EPOCHS
    try:
        data = _collect_windows(
            values=values, windows=windows, use_synthetic=use_synthetic
        )
        model = lae.build_model(
            hidden_dim=settings.ML_HIDDEN_DIM,
            latent_dim=settings.ML_LATENT_DIM,
        )
        final_loss = lae.fit_model(model, data, epochs=train_epochs)
        path = _checkpoint_path()
        lae.save_checkpoint(
            model,
            path,
            meta={
                "model_version": settings.ML_MODEL_VERSION,
                "seq_len": settings.ML_SEQ_LEN,
                "latent_dim": settings.ML_LATENT_DIM,
                "hidden_dim": settings.ML_HIDDEN_DIM,
                "final_loss": final_loss,
                "n_windows": int(data.shape[0]),
            },
        )
        _set_model(model)
        layers["train"] = {
            "ok": True,
            "epochs": train_epochs,
            "final_loss": final_loss,
            "n_windows": int(data.shape[0]),
            "checkpoint": str(path),
        }
    except Exception as exc:
        logger.exception("anomaly fit failed")
        return {
            "ok": False,
            "error": str(exc),
            "layers": {"train": {"ok": False, "error": str(exc)}},
            "model_version": settings.ML_MODEL_VERSION,
            "series_id": series_id,
        }

    try:
        layers["prefect"] = run_anomaly_flow(
            series_id=series_id,
            action="fit",
            n_windows=int(layers["train"]["n_windows"]),
            final_loss=float(layers["train"]["final_loss"]),
        )
    except Exception as exc:
        logger.exception("prefect anomaly fit failed")
        layers["prefect"] = {"ok": False, "error": str(exc)}

    layers["postgres"] = {"ok": False}
    if pool is not None:
        try:
            await ensure_anomaly_tables(pool)
            layers["postgres"] = {
                "ok": True,
                "table": "anomaly_embeddings",
                "extension": "vector",
            }
        except Exception as exc:
            logger.exception("pgvector ensure failed")
            layers["postgres"] = {"ok": False, "error": str(exc)}
    else:
        layers["postgres"] = {"ok": False, "error": "pool not connected"}

    ok = all(v.get("ok") for v in layers.values())
    return {
        "ok": ok,
        "model_version": settings.ML_MODEL_VERSION,
        "series_id": series_id,
        "layers": layers,
    }


async def score_anomaly(
    *,
    pool: asyncpg.Pool | None,
    values: list[float],
    series_id: str = "default",
    persist: bool = True,
    neighbors: int = 3,
) -> dict[str, Any]:
    layers: dict[str, Any] = {}

    if not lae.torch_available():
        return {
            "ok": False,
            "error": "PyTorch not installed — uv sync --group ml",
            "model_version": settings.ML_MODEL_VERSION,
            "series_id": series_id,
            "reconstruction_error": 0.0,
            "threshold": settings.ML_ANOMALY_THRESHOLD,
            "is_anomaly": False,
            "embedding": [],
            "embedding_id": None,
            "neighbors": [],
            "layers": {"torch": {"ok": False}},
        }

    try:
        model = _get_or_load_model()
        window = lae.pad_or_truncate(values, settings.ML_SEQ_LEN)
        scored = lae.score_window(model, window)
        is_anomaly = scored.reconstruction_error >= settings.ML_ANOMALY_THRESHOLD
        layers["model"] = {"ok": True, "checkpoint": str(_checkpoint_path())}
    except Exception as exc:
        logger.exception("anomaly score failed")
        return {
            "ok": False,
            "error": str(exc),
            "model_version": settings.ML_MODEL_VERSION,
            "series_id": series_id,
            "reconstruction_error": 0.0,
            "threshold": settings.ML_ANOMALY_THRESHOLD,
            "is_anomaly": False,
            "embedding": [],
            "embedding_id": None,
            "neighbors": [],
            "layers": {"model": {"ok": False, "error": str(exc)}},
        }

    embedding_id: str | None = None
    neighbor_rows: list[dict[str, Any]] = []
    layers["postgres"] = {"ok": False}

    if pool is not None:
        try:
            await ensure_anomaly_tables(pool)
            lit = _vector_literal(scored.embedding)

            if persist:
                embedding_id = str(uuid.uuid4())
                await pool.execute(
                    """
                    INSERT INTO anomaly_embeddings (
                        id, series_id, model_version, series_window, embedding,
                        reconstruction_error, is_anomaly, metadata
                    )
                    VALUES (
                        $1::uuid, $2, $3, $4::jsonb, $5::vector,
                        $6, $7, $8::jsonb
                    )
                    """,
                    embedding_id,
                    series_id,
                    settings.ML_MODEL_VERSION,
                    json.dumps(window.tolist()),
                    lit,
                    scored.reconstruction_error,
                    is_anomaly,
                    json.dumps({"seq_len": settings.ML_SEQ_LEN}),
                )

            if neighbors > 0:
                rows = await pool.fetch(
                    """
                    SELECT id::text, series_id, reconstruction_error, is_anomaly,
                           (embedding <=> $1::vector) AS distance
                    FROM anomaly_embeddings
                    WHERE ($2::uuid IS NULL OR id <> $2::uuid)
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                    """,
                    lit,
                    embedding_id,
                    neighbors,
                )
                neighbor_rows = [
                    {
                        "id": r["id"],
                        "series_id": r["series_id"],
                        "reconstruction_error": float(r["reconstruction_error"]),
                        "is_anomaly": bool(r["is_anomaly"]),
                        "distance": float(r["distance"]),
                    }
                    for r in rows
                ]

            layers["postgres"] = {
                "ok": True,
                "persisted": persist,
                "embedding_id": embedding_id,
                "neighbors": len(neighbor_rows),
            }
        except Exception as exc:
            logger.exception("pgvector persist/search failed")
            layers["postgres"] = {"ok": False, "error": str(exc)}
    else:
        layers["postgres"] = {"ok": False, "error": "pool not connected"}

    try:
        layers["prefect"] = run_anomaly_flow(
            series_id=series_id,
            action="score",
            n_windows=1,
            final_loss=scored.reconstruction_error,
            is_anomaly=is_anomaly,
        )
    except Exception as exc:
        logger.exception("prefect anomaly score failed")
        layers["prefect"] = {"ok": False, "error": str(exc)}

    ok = bool(layers.get("model", {}).get("ok"))
    return {
        "ok": ok,
        "model_version": settings.ML_MODEL_VERSION,
        "series_id": series_id,
        "reconstruction_error": scored.reconstruction_error,
        "threshold": settings.ML_ANOMALY_THRESHOLD,
        "is_anomaly": is_anomaly,
        "embedding": scored.embedding,
        "embedding_id": embedding_id,
        "neighbors": neighbor_rows,
        "layers": layers,
    }


async def recent_embeddings(
    pool: asyncpg.Pool | None, *, limit: int = 10
) -> list[dict[str, Any]]:
    if pool is None:
        return []
    try:
        rows = await pool.fetch(
            """
            SELECT id::text, created_at, series_id, model_version,
                   reconstruction_error, is_anomaly, series_window
            FROM anomaly_embeddings
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    except Exception:
        logger.exception("failed to list anomaly embeddings")
        return []

    out: list[dict[str, Any]] = []
    for row in rows:
        series_window = row["series_window"]
        if isinstance(series_window, str):
            series_window = json.loads(series_window)
        out.append(
            {
                "id": row["id"],
                "created_at": row["created_at"].isoformat(),
                "series_id": row["series_id"],
                "model_version": row["model_version"],
                "reconstruction_error": float(row["reconstruction_error"]),
                "is_anomaly": bool(row["is_anomaly"]),
                "window": series_window,
            }
        )
    return out
