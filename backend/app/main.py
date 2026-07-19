"""FORJD FastAPI entrypoint — lifespan, middleware, health probes, v1 router."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.v1.router import api_router
from app.core.auth import warm_jwks
from app.core.clients import create_db_pool, create_redis_client
from app.core.config import settings
from app.core.landing import render_landing
from app.core.logging import configure_logging
from app.core.rollbar import configure_rollbar
from app.core.security import ApiKeyMiddleware, SecurityHeadersMiddleware
from app.core.sentry import configure_sentry

logger = logging.getLogger("forjd.main")


# --- Lifespan: soft-connect deps, warm JWKS, sync use_cases, clean shutdown ---
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(debug=settings.DEBUG)

    # Soft-connect: local `uv run forjd` works without Compose up.
    # /ready reports whether Postgres + Redis are actually reachable.
    app.state.db_pool = await create_db_pool()
    app.state.redis = await create_redis_client()
    await warm_jwks()

    stop_worker = asyncio.Event()
    worker_task: asyncio.Task[None] | None = None
    pool = getattr(app.state, "db_pool", None)
    if pool is not None:
        try:
            from app.services import tenants as tenant_svc
            from app.services.use_cases import sync_use_cases_from_workflows

            await tenant_svc.ensure_secure_schema(pool)
            await sync_use_cases_from_workflows(pool)
        except Exception as exc:  # noqa: BLE001
            # Local boot without Postgres / migrations still allowed; /ready gates traffic.
            logger.warning("startup schema/use_cases sync skipped: %s", exc)

        if settings.PROJECTION_TICK_SECONDS > 0:
            from app.services.projection_worker import run_projection_worker

            worker_task = asyncio.create_task(run_projection_worker(pool, stop_worker))

    yield

    stop_worker.set()
    if worker_task is not None:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task

    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()

    pool = getattr(app.state, "db_pool", None)
    if pool is not None:
        await pool.close()

    try:
        from app.services.engine import close_engine_clients

        await close_engine_clients()
    except Exception as exc:  # noqa: BLE001
        logger.warning("engine client shutdown: %s", exc)


# --- App + middleware stack ---
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    lifespan=lifespan,
)

# Sentry (SDK-level, before middleware), Rollbar, then security headers, API key, CORS
configure_sentry()
configure_rollbar(app)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ApiKeyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    # DELETE required for session / service-account revoke from browser clients.
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


# --- Landing page ---
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing() -> HTMLResponse:
    """FJORD-styled API landing page with links to the interactive docs."""
    return HTMLResponse(content=render_landing())


# --- Probes ---
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness — process is up. Does not check dependencies."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/ready")
async def readiness(request: Request) -> JSONResponse:
    """Readiness — Postgres + Redis (+ optional engine) must respond."""
    checks: dict[str, bool] = {"postgres": False, "redis": False}

    pool = getattr(request.app.state, "db_pool", None)
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["postgres"] = True
        except Exception:
            checks["postgres"] = False

        if checks["postgres"] and settings.REQUIRE_RLS:
            try:
                from app.services import tenants as tenant_svc

                await tenant_svc.assert_secure_schema(pool)
                checks["schema_rls"] = True
            except Exception:
                checks["schema_rls"] = False

    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            checks["redis"] = bool(await redis.ping())
        except Exception:
            checks["redis"] = False

    # Engine probe is informational — sealed API stays ready if Postgres/Redis/RLS ok.
    # (HTTP engine may restart independently; Pathway/PyO3 remain soft-fallbacks.)
    engine_meta: dict[str, Any] | None = None
    if settings.ENGINE_URL.strip():
        from app.services import engine as engine_svc

        remote = await engine_svc.remote_version()
        engine_ok = bool(remote and remote.get("service") == "forjd-engine")
        engine_meta = {**(remote or {}), "ok": engine_ok}

    ready = all(checks.values())
    body: dict[str, Any] = {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
    }
    if engine_meta is not None:
        body["engine"] = engine_meta
    return JSONResponse(content=body, status_code=200 if ready else 503)
