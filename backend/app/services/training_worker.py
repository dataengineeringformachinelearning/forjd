"""Scheduled ML training + optional Hugging Face model publishing worker.

Each tick finds tenants with recent ``stream_results`` and, when their newest
NorseSSN ``training_runs`` row is older than the refresh window, retrains the
SLA regressor and threat model, then fits and scores a tenant-scoped NorseSSN
using real telemetry only. When ``HF_MODEL_REPO_ID`` + ``HF_TOKEN`` are
configured, fresh ``.pt`` artifacts are published to the Hugging Face Hub under
hashed-tenant paths (never tenant UUIDs or ciphertext).
(Supersedes the former DEML-local daily training loop.)
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import math
from pathlib import Path
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.core.worker_health import WorkerHealthRegistry
from app.services.ml.lstm_autoencoder import torch_available

logger = logging.getLogger("forjd.training.worker")

WORKER_NAME = "ml-training"
# Tenants with results inside this window keep their models fresh.
ACTIVE_WINDOW_DAYS = 7
# Minimum series length for seq_len 16 plus multiple next-observation labels.
MIN_SERIES_LEN = 24
# Hugging Face prefixes (matched by scripts/verify_huggingface_models.py in DEML).
HF_FAMILY_PATHS = {
    "sla": ("sla_models", "sla_model.pt"),
    "threat": ("threat_models", "threat_model.pt"),
}
HF_TEMPORAL_PREFIX = "temporal_models"


# --- Tenant discovery (activity-based; keeps runaway training bounded) ---
async def _tenants_due_training(pool: asyncpg.Pool) -> list[UUID]:
    rows = await pool.fetch(
        """
        SELECT sr.tenant_id
        FROM (
            SELECT DISTINCT tenant_id FROM stream_results
            WHERE created_at >= NOW() - make_interval(days => $1)
        ) sr
        LEFT JOIN LATERAL (
            SELECT MAX(temporal.created_at) AS newest
            FROM (
                SELECT score.created_at
                FROM ml_scores score
                WHERE score.tenant_id = sr.tenant_id
                  AND score.family = 'norse_ssn'
                UNION ALL
                SELECT run.created_at
                FROM training_runs run
                WHERE run.tenant_id = sr.tenant_id
                  AND (run.family = 'norse_ssn' OR run.model_name = 'norse_ssn')
                  AND run.status = 'insufficient_data'
            ) temporal
        ) latest ON TRUE
        WHERE latest.newest IS NULL
           OR latest.newest < NOW() - ($2::float8 * INTERVAL '1 second')
        """,
        ACTIVE_WINDOW_DAYS,
        settings.TRAINING_REFRESH_SECONDS,
    )
    return [UUID(str(r["tenant_id"])) for r in rows]


# --- Temporal series (score history feeds the forecasters) ---
async def _score_series(pool: asyncpg.Pool, tenant_id: UUID) -> list[float]:
    rows = await pool.fetch(
        """
        SELECT score::float AS score FROM stream_results
        WHERE tenant_id = $1::uuid AND score IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 256
        """,
        str(tenant_id),
    )
    series = [float(r["score"]) for r in reversed(rows)]
    return [value for value in series if math.isfinite(value)]


# --- One tenant: train all torch families that FORJD owns ---
async def _train_tenant(pool: asyncpg.Pool, tenant_id: UUID) -> dict[str, bool]:
    from app.services.ml import norse_ssn
    from app.services.ml import store as ml_store
    from app.services.ml import supabase_bridge as ml_sb
    from app.services.ml.sla_model import train_tenant_sla
    from app.services.ml.threat_model import train_threat_model

    trained: dict[str, bool] = {}
    short = str(tenant_id)[:8]

    try:
        result = await train_tenant_sla(pool, tenant_id=tenant_id)
        trained["sla"] = bool(result.get("ok"))
    except Exception:  # noqa: BLE001 — auxiliary model must not block temporal truth
        trained["sla"] = False
        logger.exception("sla training failed tenant=%s", short)

    try:
        result = await train_threat_model(pool, tenant_id=tenant_id)
        trained["threat"] = bool(result.get("ok"))
    except Exception:  # noqa: BLE001 — auxiliary model must not block temporal truth
        trained["threat"] = False
        logger.exception("threat training failed tenant=%s", short)

    series = await _score_series(pool, tenant_id)
    if len(series) < MIN_SERIES_LEN:
        await ml_store.record_training_run(
            pool,
            tenant_id=str(tenant_id),
            family="norse_ssn",
            model_name="norse_ssn",
            metrics={"sample_count": len(series), "min_required": MIN_SERIES_LEN},
            status="insufficient_data",
        )
        trained["temporal"] = False
        trained["norse_ssn"] = False
    else:
        fit_result = await asyncio.to_thread(
            norse_ssn.fit,
            series=series,
            tenant_id=str(tenant_id),
        )
        await ml_sb.persist_fit(
            pool,
            model_id="norse_ssn",
            tenant_id=str(tenant_id),
            result=fit_result,
        )
        score_result = await asyncio.to_thread(
            norse_ssn.score,
            series=series,
            tenant_id=str(tenant_id),
        )
        await ml_sb.persist_score(
            pool,
            model_id="norse_ssn",
            tenant_id=str(tenant_id),
            result=score_result,
        )
        temporal_ok = bool(fit_result.get("ok") and score_result.get("ok"))
        trained["temporal"] = temporal_ok
        trained["norse_ssn"] = temporal_ok

    logger.info("training complete tenant=%s trained=%s", short, trained)
    return trained


# --- Hugging Face publishing (config-gated; hashed tenant namespacing) ---
def _hf_configured() -> bool:
    return bool(settings.HF_MODEL_REPO_ID and settings.HF_TOKEN)


def _tenant_hash(tenant_id: UUID) -> str:
    return hashlib.sha256(str(tenant_id).encode()).hexdigest()[:16]


def _publish_tenant_artifacts(tenant_id: UUID) -> int:
    """Upload fresh .pt artifacts for one tenant; returns files published."""
    try:
        from huggingface_hub import HfApi
    except ImportError:  # pragma: no cover - ml group ships huggingface_hub
        logger.warning("huggingface_hub not installed; skipping model publish")
        return 0

    api = HfApi(token=settings.HF_TOKEN)
    hashed = _tenant_hash(tenant_id)
    published = 0
    uploads: list[tuple[Path, str]] = []

    for family, (prefix, filename) in HF_FAMILY_PATHS.items():
        local = Path(settings.ML_MODEL_DIR) / family / str(tenant_id) / filename
        if local.is_file():
            uploads.append((local, f"{prefix}/{hashed}_{filename}"))

    for family in ("forecasting", "norse_ssn"):
        temporal_dir = Path(settings.ML_MODEL_DIR) / family / str(tenant_id)
        if temporal_dir.is_dir():
            for artifact in sorted(temporal_dir.glob("*.pt")):
                uploads.append((artifact, f"{HF_TEMPORAL_PREFIX}/{hashed}_{artifact.name}"))

    for local, remote in uploads:
        api.upload_file(
            path_or_fileobj=str(local),
            path_in_repo=remote,
            repo_id=settings.HF_MODEL_REPO_ID,
            repo_type="model",
        )
        published += 1
    return published


# --- One tick ---
async def tick_training(pool: asyncpg.Pool) -> int:
    if not torch_available():
        logger.debug("torch unavailable; training tick skipped")
        return 0
    tenants = await _tenants_due_training(pool)
    for tenant_id in tenants:
        try:
            await _train_tenant(pool, tenant_id)
        except Exception:  # noqa: BLE001 - one tenant must not block the rest
            logger.exception("training failed tenant=%s", str(tenant_id)[:8])
            continue
        if _hf_configured():
            try:
                count = await asyncio.to_thread(_publish_tenant_artifacts, tenant_id)
                logger.info(
                    "hf publish tenant=%s files=%s repo=%s",
                    str(tenant_id)[:8],
                    count,
                    settings.HF_MODEL_REPO_ID,
                )
            except Exception:  # noqa: BLE001 - publish failures retry next tick
                logger.exception("hf publish failed tenant=%s", str(tenant_id)[:8])
    return len(tenants)


# --- Supervised loop ---
async def run_training_worker(
    pool: asyncpg.Pool,
    stop_event: asyncio.Event,
    *,
    interval_seconds: float | None = None,
    health: WorkerHealthRegistry | None = None,
) -> None:
    interval = interval_seconds or settings.TRAINING_TICK_SECONDS
    logger.info(
        "ml training worker started interval=%ss hf_publish=%s",
        interval,
        _hf_configured(),
    )
    while not stop_event.is_set():
        try:
            trained = await tick_training(pool)
            if health is not None:
                health.succeeded(WORKER_NAME)
            if trained:
                logger.info("training tick tenants=%s", trained)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - supervised retry loop
            logger.exception("training tick failed")
            if health is not None:
                health.failed(WORKER_NAME, exc)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
