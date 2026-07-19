"""Optional background projection tick — catch-up for durable watermarks.

Uses the service-role pool via `run_projection_core` (no synthetic AuthUser).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.core.worker_health import WorkerHealthRegistry
from app.services import projections as proj_svc
from app.workflows.registry import all_workflows

logger = logging.getLogger("forjd.projection_worker")


# --- Keyset-page tenants with sealed events ---
async def _tenant_ids_with_events(
    pool: asyncpg.Pool,
    *,
    after_tenant_id: UUID | None = None,
    limit: int = 50,
) -> list[UUID]:
    rows = await pool.fetch(
        """
        SELECT DISTINCT tenant_id
        FROM telemetry_events
        WHERE ($1::uuid IS NULL OR tenant_id > $1::uuid)
        ORDER BY tenant_id
        LIMIT $2
        """,
        str(after_tenant_id) if after_tenant_id else None,
        limit,
    )
    return [UUID(str(r["tenant_id"])) for r in rows]


# --- One catch-up pass (service role; no impersonation) ---
async def tick_projections(pool: asyncpg.Pool) -> dict[str, Any]:
    """Advance projections for tenants that have sealed events."""
    workflows = [w for w in all_workflows() if w.enabled]
    tenant_count = 0
    processed = 0
    written = 0
    failures = 0
    after_tenant_id: UUID | None = None
    page_size = 50
    while True:
        tenants = await _tenant_ids_with_events(
            pool,
            after_tenant_id=after_tenant_id,
            limit=page_size,
        )
        if not tenants:
            break
        tenant_count += len(tenants)
        for tid in tenants:
            for wf in workflows:
                try:
                    result = await proj_svc.run_projection_core(
                        pool,
                        tenant_id=tid,
                        workflow_id=wf.id,
                        limit=200,
                    )
                    processed += int(result.get("processed") or 0)
                    written += int(result.get("written") or 0)
                    if not result.get("ok"):
                        failures += 1
                        logger.warning(
                            "projection tick unsuccessful tenant=%s workflow=%s error=%s",
                            tid,
                            wf.id,
                            result.get("error") or "unknown",
                        )
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    logger.warning(
                        "projection tick failed tenant=%s workflow=%s: %s",
                        tid,
                        wf.id,
                        exc,
                    )
        after_tenant_id = tenants[-1]
        if len(tenants) < page_size:
            break
    return {
        "ok": failures == 0,
        "tenants": tenant_count,
        "processed": processed,
        "written": written,
        "failures": failures,
    }


# --- Lifespan background loop ---
async def run_projection_worker(
    pool: asyncpg.Pool,
    stop: asyncio.Event,
    *,
    health: WorkerHealthRegistry | None = None,
) -> None:
    interval = float(settings.PROJECTION_TICK_SECONDS or 0)
    if interval <= 0:
        return
    logger.info("projection worker started (interval=%.1fs)", interval)
    while not stop.is_set():
        try:
            summary = await tick_projections(pool)
            if summary.get("processed"):
                logger.info("projection tick %s", summary)
            if health is not None:
                if summary.get("ok"):
                    health.succeeded("projection-catchup")
                else:
                    health.failed(
                        "projection-catchup",
                        RuntimeError("projection tick reported item failures"),
                    )
        except Exception as exc:  # noqa: BLE001
            if health is not None:
                health.failed("projection-catchup", exc)
            logger.exception("projection worker tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue
    logger.info("projection worker stopped")
