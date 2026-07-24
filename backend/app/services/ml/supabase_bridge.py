"""Bridge ML fit/score results ↔ Supabase (training_runs, embeddings, ml_scores).

Called from the API after registry dispatch. Keeps model modules free of I/O
while ensuring every tenant-scoped run lands in Postgres under RLS.
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from app.services.ml import store as ml_store

logger = logging.getLogger("forjd.ml.supabase")


# --- Hydrate missing inputs from stream_results metadata ---
async def hydrate_fit_kwargs(
    pool: asyncpg.Pool | None,
    model_id: str,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    if pool is None:
        return kwargs
    tenant_id = kwargs.get("tenant_id")
    if not tenant_id:
        return kwargs

    out = dict(kwargs)
    if model_id in {"classical_anomaly", "threat_ensemble"} and not out.get("features"):
        feats = await ml_store.features_from_stream_results(pool, tenant_id=str(tenant_id))
        if feats:
            out["features"] = feats
            if model_id == "threat_ensemble" and not out.get("labels"):
                # Weak labels from is_anomaly bit packed in feature[1].
                out["labels"] = [1 if row[1] >= 0.5 else 0 for row in feats]
            logger.info("hydrated %s features from stream_results n=%s", model_id, len(feats))

    if model_id in {
        "lstm_autoencoder",
        "transformer_anomaly",
        "forecasting",
        "norse_ssn",
    } and not out.get("series"):
        series = await ml_store.series_from_stream_results(pool, tenant_id=str(tenant_id))
        if len(series) >= 8:
            out["series"] = series
            logger.info("hydrated %s series from stream_results n=%s", model_id, len(series))

    return out


# --- Persist fit artifacts ---
async def persist_fit(
    pool: asyncpg.Pool | None,
    *,
    model_id: str,
    tenant_id: str | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    if pool is None or not tenant_id:
        result = dict(result)
        result.setdefault("supabase", {"persisted": False, "reason": "no tenant/pool"})
        return result

    await ml_store.ensure_ml_store_schema(pool)
    metrics = {
        k: v
        for k, v in result.items()
        if k not in {"ok", "paths", "path", "supabase"} and not isinstance(v, (list, dict))
    }
    # Keep small nested metrics (e.g. losses) without dumping huge payloads.
    for key in ("losses", "models", "n_samples", "n_windows", "n_points", "final_loss"):
        if key in result:
            metrics[key] = result[key]

    artifact: str | None = None
    if result.get("path"):
        artifact = str(result["path"])
    elif isinstance(result.get("paths"), dict) and result["paths"]:
        metrics["paths"] = result["paths"]
        artifact = str(next(iter(result["paths"].values())))

    run_id = await ml_store.record_training_run(
        pool,
        tenant_id=tenant_id,
        family=model_id,
        model_name=str(result.get("model") or model_id),
        metrics=metrics,
        artifact_path=artifact,
        status="completed" if result.get("ok") else "failed",
    )
    out = dict(result)
    out["supabase"] = {
        "persisted": True,
        "training_run_id": run_id,
        "table": "training_runs",
    }
    return out


# --- Persist score / encode outputs ---
async def persist_score(
    pool: asyncpg.Pool | None,
    *,
    model_id: str,
    tenant_id: str | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    if pool is None or not tenant_id:
        result = dict(result)
        result.setdefault("supabase", {"persisted": False, "reason": "no tenant/pool"})
        return result

    await ml_store.ensure_ml_store_schema(pool)
    out = dict(result)
    persisted: dict[str, Any] = {"persisted": True}

    # Latent vectors → embedding_vectors (pgvector)
    embedding = result.get("embedding")
    if (
        isinstance(embedding, list)
        and embedding
        and all(isinstance(x, (int, float)) for x in embedding)
    ):
        emb_id = await ml_store.persist_embedding(
            pool,
            tenant_id=tenant_id,
            embedding=[float(x) for x in embedding],
            reconstruction_error=result.get("reconstruction_error"),
            is_anomaly=bool(result.get("is_anomaly")),
            series_id=str(result.get("family") or model_id),
            model_version=str(result.get("model_version") or model_id),
            metadata={"family": model_id},
        )
        persisted["embedding_id"] = emb_id
        try:
            persisted["neighbors"] = await ml_store.nearest_embeddings(
                pool,
                tenant_id=tenant_id,
                embedding=[float(x) for x in embedding],
                limit=5,
            )
        except Exception as exc:  # pragma: no cover - pgvector optional locally
            logger.warning("pgvector NN skipped: %s", exc)

    # Batch embeddings from EventEncoder
    embeddings = result.get("embeddings")
    if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
        ids = []
        for vec in embeddings[:20]:
            eid = await ml_store.persist_embedding(
                pool,
                tenant_id=tenant_id,
                embedding=[float(x) for x in vec],
                series_id="event_encoder",
                model_version=model_id,
                metadata={"family": model_id, "backend": result.get("backend")},
            )
            ids.append(eid)
        persisted["embedding_ids"] = ids

    # Scalar / row scores → ml_scores
    score_rows: list[dict[str, Any]] = []
    if "results" in result and isinstance(result["results"], list):
        for row in result["results"]:
            score_rows.append(
                {
                    "model_name": model_id,
                    "score": row.get("score"),
                    "is_anomaly": bool(row.get("is_anomaly") or row.get("is_threat") or False),
                    "features": {
                        k: v
                        for k, v in row.items()
                        if k not in {"features", "metadata"}
                        and isinstance(v, (int, float, bool, str))
                    },
                    "metadata": {"family": model_id},
                }
            )
    elif result.get("score") is not None or result.get("reconstruction_error") is not None:
        score_rows.append(
            {
                "model_name": str(result.get("model") or model_id),
                "score": result.get("score", result.get("reconstruction_error")),
                "is_anomaly": bool(result.get("is_anomaly") or False),
                "features": {
                    k: result[k]
                    for k in (
                        "p99_forecast",
                        "threshold",
                        "uses_norse",
                        "backend",
                        "kind",
                        "sample_count",
                        "seq_len",
                    )
                    if k in result
                },
                "metadata": {
                    "family": model_id,
                    "forecast": result.get("forecast"),
                },
            }
        )

    if score_rows:
        n = await ml_store.persist_scores(
            pool, tenant_id=tenant_id, family=model_id, rows=score_rows
        )
        persisted["ml_scores_written"] = n
        persisted["table"] = "ml_scores"

    out["supabase"] = persisted
    return out
