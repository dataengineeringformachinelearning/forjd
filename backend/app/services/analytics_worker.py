"""Continuous analytics rollup + ML score refresh worker.

Each tick finds tenants with fresh ``stream_results`` and (a) upserts current +
previous hour rollups into ``aggregated_analytics`` so the overview / CES /
temporal forecast stay live, and (b) refreshes classical-anomaly ``ml_scores``
so threat reports have model output without a manual /ml call. Metadata only —
the worker never touches sealed ciphertext. (Supersedes the former DEML-local
aggregation loop.)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.core.worker_health import WorkerHealthRegistry
from app.services import analytics as analytics_svc
from app.services.ml import store as ml_store
from app.services.ml import supabase_bridge as ml_sb
from app.services.ml.common import sklearn_available

logger = logging.getLogger("forjd.analytics.worker")

WORKER_NAME = "analytics-rollup"
# Look-back window for "active" tenants; covers the previous-hour bucket too.
ACTIVE_WINDOW_HOURS = 2
# Minimum rows before a classical fit is meaningful.
MIN_ML_SAMPLES = 8


# --- Active tenant discovery ---
async def _active_tenants(pool: asyncpg.Pool) -> list[UUID]:
    rows = await pool.fetch(
        """
        SELECT DISTINCT tenant_id FROM stream_results
        WHERE created_at >= NOW() - make_interval(hours => $1)
        """,
        ACTIVE_WINDOW_HOURS,
    )
    return [UUID(str(r["tenant_id"])) for r in rows]


# --- Hourly rollups (current + previous bucket) ---
async def _rollup_tenant(pool: asyncpg.Pool, tenant_id: UUID) -> None:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for bucket in (now - timedelta(hours=1), now):
        await analytics_svc.aggregate_hour(pool, tenant_id=tenant_id, bucket_start=bucket)


# --- Classical anomaly ML refresh (fit + score → ml_scores) ---
async def _ml_scores_fresh(pool: asyncpg.Pool, tenant_id: UUID) -> bool:
    newest = await pool.fetchval(
        """
        SELECT MAX(created_at) FROM ml_scores
        WHERE tenant_id = $1::uuid AND family = 'classical_anomaly'
        """,
        str(tenant_id),
    )
    if newest is None:
        return False
    age = (datetime.now(UTC) - newest).total_seconds()
    return age < settings.ANALYTICS_ML_REFRESH_SECONDS


async def _refresh_ml_scores(pool: asyncpg.Pool, tenant_id: UUID) -> None:
    """Fit + score classical anomaly from stream_results metadata (never ciphertext)."""
    if not sklearn_available() or await _ml_scores_fresh(pool, tenant_id):
        return
    feats = await ml_store.features_from_stream_results(pool, tenant_id=str(tenant_id))
    if len(feats) < MIN_ML_SAMPLES:
        return
    from app.services.ml import classical_anomaly

    # Blocking sklearn fit/score off the event loop.
    fit_result = await asyncio.to_thread(
        classical_anomaly.fit, features=feats, tenant_id=str(tenant_id)
    )
    await ml_sb.persist_fit(
        pool, model_id="classical_anomaly", tenant_id=str(tenant_id), result=fit_result
    )
    score_result = await asyncio.to_thread(
        classical_anomaly.score, features=feats, tenant_id=str(tenant_id)
    )
    await ml_sb.persist_score(
        pool, model_id="classical_anomaly", tenant_id=str(tenant_id), result=score_result
    )
    logger.info("ml refresh tenant=%s samples=%s", str(tenant_id)[:8], len(feats))


# --- One tick ---
async def tick_analytics_rollups(pool: asyncpg.Pool) -> int:
    tenants = await _active_tenants(pool)
    for tenant_id in tenants:
        await _rollup_tenant(pool, tenant_id)
        try:
            await _refresh_ml_scores(pool, tenant_id)
        except Exception:  # noqa: BLE001 - ML refresh must never block rollups
            logger.exception("ml refresh failed tenant=%s", str(tenant_id)[:8])
    return len(tenants)


# --- Supervised loop ---
async def run_analytics_worker(
    pool: asyncpg.Pool,
    stop_event: asyncio.Event,
    *,
    interval_seconds: float | None = None,
    health: WorkerHealthRegistry | None = None,
) -> None:
    interval = interval_seconds or settings.ANALYTICS_ROLLUP_INTERVAL_SECONDS
    logger.info("analytics rollup worker started interval=%ss", interval)
    while not stop_event.is_set():
        try:
            processed: dict[str, Any] = {"tenants": await tick_analytics_rollups(pool)}
            if health is not None:
                health.succeeded(WORKER_NAME)
            logger.debug("analytics rollup tick %s", processed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - supervised retry loop
            logger.exception("analytics rollup tick failed")
            if health is not None:
                health.failed(WORKER_NAME, exc)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
