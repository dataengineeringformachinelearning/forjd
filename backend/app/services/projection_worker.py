"""Optional background projection tick — catch-up for durable watermarks."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
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


# --- One catch-up pass (system user; membership bypass via service path) ---
async def tick_projections(pool: asyncpg.Pool) -> dict[str, Any]:
    """Advance projections for tenants that have sealed events.

    Uses a synthetic system AuthUser only for require_member-compatible APIs —
    worker path calls run_projection internals via service role after listing.
    """
    tenants = await _tenant_ids_with_events(pool)
    workflows = [w for w in all_workflows() if w.enabled]
    processed = 0
    written = 0
    # System actor: membership check needs a real member — use owner of each tenant.
    for tid in tenants:
        owner = await pool.fetchval(
            """
            SELECT user_id::text FROM tenant_members
            WHERE tenant_id = $1::uuid AND role = 'owner'
            LIMIT 1
            """,
            str(tid),
        )
        if not owner:
            continue
        user = AuthUser(
            user_id=owner, email=None, role="authenticated", raw_claims={}
        )
        for wf in workflows:
            try:
                result = await proj_svc.run_projection(
                    pool,
                    user=user,
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
    return {"ok": True, "tenants": len(tenants), "processed": processed, "written": written}


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
