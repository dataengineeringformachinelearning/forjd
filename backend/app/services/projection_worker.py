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
from app.services import projections as proj_svc
from app.workflows.registry import all_workflows

logger = logging.getLogger("forjd.projection_worker")


# --- List tenants with recent sealed events ---
async def _tenant_ids_with_events(pool: asyncpg.Pool, *, limit: int = 50) -> list[UUID]:
    rows = await pool.fetch(
        """
        SELECT DISTINCT tenant_id
        FROM telemetry_events
        ORDER BY tenant_id
        LIMIT $1
        """,
        limit,
    )
    return [UUID(str(r["tenant_id"])) for r in rows]


# --- One catch-up pass (service role; no impersonation) ---
async def tick_projections(pool: asyncpg.Pool) -> dict[str, Any]:
    """Advance projections for tenants that have sealed events."""
    tenants = await _tenant_ids_with_events(pool)
    workflows = [w for w in all_workflows() if w.enabled]
    processed = 0
    written = 0
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
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "projection tick failed tenant=%s workflow=%s: %s",
                    tid,
                    wf.id,
                    exc,
                )
    return {
        "ok": True,
        "tenants": len(tenants),
        "processed": processed,
        "written": written,
    }


# --- Lifespan background loop ---
async def run_projection_worker(pool: asyncpg.Pool, stop: asyncio.Event) -> None:
    interval = float(settings.PROJECTION_TICK_SECONDS or 0)
    if interval <= 0:
        return
    logger.info("projection worker started (interval=%.1fs)", interval)
    while not stop.is_set():
        try:
            summary = await tick_projections(pool)
            if summary.get("processed"):
                logger.info("projection tick %s", summary)
        except Exception:  # noqa: BLE001
            logger.exception("projection worker tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue
    logger.info("projection worker stopped")
