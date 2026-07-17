"""FORJD FastAPI entrypoint — lifespan, middleware, health probes, v1 router."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.auth import warm_jwks
from app.core.clients import create_db_pool, create_redis_client
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.rollbar import configure_rollbar
from app.core.security import ApiKeyMiddleware, SecurityHeadersMiddleware


# --- Lifespan: soft-connect deps, warm JWKS, clean shutdown ---
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(debug=settings.DEBUG)

    # Soft-connect: local `uv run forjd` works without Compose up.
    # /ready reports whether Postgres + Redis are actually reachable.
    app.state.db_pool = await create_db_pool()
    app.state.redis = await create_redis_client()
    await warm_jwks()

    yield

    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()

    pool = getattr(app.state, "db_pool", None)
    if pool is not None:
        await pool.close()


# --- App + middleware stack ---
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    lifespan=lifespan,
)

# Rollbar first (when token set), then security headers, optional API key, CORS
configure_rollbar(app)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ApiKeyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


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
    """Readiness — Postgres + Redis must respond. Returns 503 if either is down."""
    checks: dict[str, bool] = {"postgres": False, "redis": False}

    pool = getattr(request.app.state, "db_pool", None)
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["postgres"] = True
        except Exception:
            checks["postgres"] = False

    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            checks["redis"] = bool(await redis.ping())
        except Exception:
            checks["redis"] = False

    ready = all(checks.values())
    body: dict[str, Any] = {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
    }
    return JSONResponse(content=body, status_code=200 if ready else 503)
