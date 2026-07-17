"""Stack status for the PoC dashboard (does not mutate state)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.core.config import settings
from app.services import engine
from app.services.anomaly import ml_status

router = APIRouter(prefix="/stack", tags=["stack"])


@router.get("")
async def stack_status(request: Request) -> dict[str, Any]:
    engine_check = engine.engine_status()
    if engine_check.get("mode") == "http":
        remote = await engine.remote_version()
        if remote is not None:
            engine_check = {
                **engine_check,
                "ok": "error" not in remote,
                "remote": remote,
            }

    checks: dict[str, Any] = {
        "api": {"ok": True, "name": settings.PROJECT_NAME, "version": settings.PROJECT_VERSION},
        "engine": engine_check,
        "postgres": {"ok": False},
        "dragonfly": {"ok": False},
        "ml": ml_status(),
    }

    pool = getattr(request.app.state, "db_pool", None)
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
                ext = await conn.fetchval(
                    "SELECT extname FROM pg_extension WHERE extname = 'vector'"
                )
            checks["postgres"] = {
                "ok": True,
                "backend": "supabase-or-postgres",
                "pgvector": ext == "vector",
            }
        except Exception as exc:
            checks["postgres"] = {"ok": False, "error": str(exc)}

    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            checks["dragonfly"] = {"ok": bool(await redis.ping()), "backend": "dragonfly"}
        except Exception as exc:
            checks["dragonfly"] = {"ok": False, "error": str(exc)}

    # Core stack readiness ignores optional ML (torch may be absent in slim images).
    core_ok = all(
        v.get("ok") for k, v in checks.items() if k != "ml"
    )
    return {
        "ok": core_ok,
        "environment": settings.ENVIRONMENT,
        "checks": checks,
    }
