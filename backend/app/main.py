"""FORJD FastAPI entrypoint — lifespan, middleware, health probes, v1 router."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.auth import warm_jwks
from app.core.clients import create_db_pool, create_redis_client
from app.core.config import settings
from app.core.http_errors import register_exception_handlers
from app.core.ingest_body_limit import IngestBodyLimitMiddleware
from app.core.ingest_limits import ingest_write_paths
from app.core.landing_page import render_landing
from app.core.logging import configure_logging
from app.core.rate_limit import PublicRateLimitMiddleware
from app.core.request_context import RequestContextMiddleware
from app.core.rollbar import configure_rollbar
from app.core.security import (
    ApiKeyMiddleware,
    HttpsRedirectMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.sentry import configure_sentry
from app.core.worker_health import WorkerHealthRegistry

logger = logging.getLogger("forjd.main")


def _start_worker(
    app: FastAPI,
    name: str,
    coroutine_factory: Any,
    *,
    stale_after_seconds: float,
) -> None:
    """Start one named worker once; replace an unexpectedly exited task."""
    tasks: dict[str, asyncio.Task[None]] = app.state.worker_tasks
    existing = tasks.get(name)
    if existing is not None and not existing.done():
        return
    if existing is not None:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            error = existing.exception()
            if error is not None:
                logger.error(
                    "background worker exited name=%s error_type=%s", name, type(error).__name__
                )
    app.state.worker_health.started(name, stale_after_seconds=stale_after_seconds)
    tasks[name] = asyncio.create_task(coroutine_factory(), name=f"forjd-{name}")


async def _prepare_pool(app: FastAPI, pool: Any) -> None:
    """Run one-time schema/workflow preparation for each concrete pool."""
    pool_identity = id(pool)
    if pool_identity in app.state.prepared_pool_ids:
        return
    async with app.state.worker_lock:
        if pool_identity in app.state.prepared_pool_ids:
            return
        from app.services import tenants as tenant_svc
        from app.services.use_cases import sync_use_cases_from_workflows

        await tenant_svc.ensure_secure_schema(pool)
        await sync_use_cases_from_workflows(pool)
        app.state.prepared_pool_ids.add(pool_identity)


async def _ensure_background_workers(app: FastAPI, pool: Any | None) -> None:
    """Supervise all durable workers, including after lazy DB recovery."""
    if app.state.worker_stop.is_set():
        return

    from app.services.ingest_processing import (
        INGEST_PROCESSING_LEASE_SECONDS,
        run_ingest_processing_worker,
    )

    # Interval 0 = disabled (status-continuous / idle-accept cuts).
    if settings.INGEST_PROCESSING_INTERVAL_SECONDS > 0:
        _start_worker(
            app,
            "ingest-processing",
            lambda: run_ingest_processing_worker(
                lambda: getattr(app.state, "db_pool", None),
                app.state.worker_stop,
                interval_seconds=settings.INGEST_PROCESSING_INTERVAL_SECONDS,
                batch_size=settings.INGEST_PROCESSING_BATCH_SIZE,
                health=app.state.worker_health,
            ),
            stale_after_seconds=max(
                INGEST_PROCESSING_LEASE_SECONDS * 2,
                settings.INGEST_PROCESSING_INTERVAL_SECONDS * 4,
            ),
        )
    if pool is None:
        return

    from app.services.exports import run_export_worker
    from app.services.playbooks import run_playbook_retry_worker

    if settings.SOAR_WORKER_INTERVAL_SECONDS > 0:
        _start_worker(
            app,
            "soar-retries",
            lambda: run_playbook_retry_worker(
                pool,
                app.state.worker_stop,
                interval_seconds=settings.SOAR_WORKER_INTERVAL_SECONDS,
                batch_size=settings.SOAR_WORKER_BATCH_SIZE,
                health=app.state.worker_health,
            ),
            stale_after_seconds=max(600.0, settings.SOAR_WORKER_INTERVAL_SECONDS * 4),
        )
    if settings.EXPORT_WORKER_INTERVAL_SECONDS > 0:
        _start_worker(
            app,
            "exports",
            lambda: run_export_worker(
                pool,
                app.state.worker_stop,
                health=app.state.worker_health,
            ),
            stale_after_seconds=max(600.0, settings.EXPORT_WORKER_INTERVAL_SECONDS * 4),
        )
    if settings.ANALYTICS_ROLLUP_INTERVAL_SECONDS > 0:
        from app.services.analytics_worker import run_analytics_worker

        _start_worker(
            app,
            "analytics-rollup",
            lambda: run_analytics_worker(
                pool,
                app.state.worker_stop,
                health=app.state.worker_health,
            ),
            stale_after_seconds=max(600.0, settings.ANALYTICS_ROLLUP_INTERVAL_SECONDS * 4),
        )
    if settings.TRAINING_TICK_SECONDS > 0:
        from app.services.training_worker import run_training_worker

        _start_worker(
            app,
            "ml-training",
            lambda: run_training_worker(
                pool,
                app.state.worker_stop,
                health=app.state.worker_health,
            ),
            stale_after_seconds=max(7200.0, settings.TRAINING_TICK_SECONDS * 4),
        )
    if settings.RETENTION_SWEEP_INTERVAL_SECONDS > 0:
        from app.services.retention import run_retention_worker

        _start_worker(
            app,
            "retention",
            lambda: run_retention_worker(
                pool,
                app.state.worker_stop,
                health=app.state.worker_health,
            ),
            stale_after_seconds=max(7200.0, settings.RETENTION_SWEEP_INTERVAL_SECONDS * 4),
        )
    if settings.PROJECTION_TICK_SECONDS > 0:
        from app.services.projection_worker import run_projection_worker

        _start_worker(
            app,
            "projection-catchup",
            lambda: run_projection_worker(
                pool,
                app.state.worker_stop,
                health=app.state.worker_health,
            ),
            stale_after_seconds=max(3600.0, settings.PROJECTION_TICK_SECONDS * 4),
        )


async def _verify_worker_contracts(app: FastAPI, pool: Any) -> None:
    """Fail readiness when an enabled durable worker's schema is incomplete."""
    pool_identity = id(pool)
    verified_pools: dict[int, Any] = app.state.verified_worker_contract_pools
    if verified_pools.get(pool_identity) is pool:
        return

    async with app.state.worker_lock:
        if verified_pools.get(pool_identity) is pool:
            return
        if settings.INGEST_PROCESSING_INTERVAL_SECONDS > 0:
            from app.services.ingest_processing import ensure_ingest_processing_schema

            await ensure_ingest_processing_schema(pool)
        if settings.SOAR_WORKER_INTERVAL_SECONDS > 0:
            from app.services.playbooks import ensure_playbook_schema
            from app.services.siem import ensure_siem_schema

            await ensure_siem_schema(pool)
            await ensure_playbook_schema(pool)
        if settings.EXPORT_WORKER_INTERVAL_SECONDS > 0:
            from app.services.exports import ensure_export_schema

            await ensure_export_schema(pool)
        verified_pools[pool_identity] = pool


async def _runtime_readiness_checks_once(app: FastAPI, pool: Any) -> dict[str, bool]:
    """Probe and prepare one concrete runtime for a readiness request."""
    checks = {
        "postgres": False,
        "runtime_setup": False,
        "worker_contracts": False,
    }
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["postgres"] = True
    except Exception:
        return checks

    if settings.REQUIRE_RLS:
        try:
            from app.services import tenants as tenant_svc

            await tenant_svc.assert_secure_schema(pool)
            checks["schema_rls"] = True
        except Exception:
            checks["schema_rls"] = False

    try:
        await _prepare_pool(app, pool)
        await _verify_worker_contracts(app, pool)
        checks["worker_contracts"] = True
        await _ensure_background_workers(app, pool)
        checks["runtime_setup"] = True
    except Exception:
        logger.exception("runtime setup failed during readiness")
    return checks


async def _runtime_readiness_checks(app: FastAPI, pool: Any) -> dict[str, bool]:
    """Coalesce overlapping first-readiness setup onto one shared task."""
    lock: asyncio.Lock = app.state.runtime_readiness_lock
    async with lock:
        task: asyncio.Task[dict[str, bool]] | None = app.state.runtime_readiness_task
        if task is None or task.done():
            task = asyncio.create_task(
                _runtime_readiness_checks_once(app, pool),
                name="forjd-runtime-readiness",
            )
            app.state.runtime_readiness_task = task

    try:
        return await asyncio.shield(task)
    finally:
        if task.done():
            async with lock:
                if app.state.runtime_readiness_task is task:
                    app.state.runtime_readiness_task = None


def _worker_health(app: FastAPI) -> tuple[bool, dict[str, dict[str, Any]]]:
    # Only expect workers that are configured to run (interval > 0).
    expected: set[str] = set()
    if settings.INGEST_PROCESSING_INTERVAL_SECONDS > 0:
        expected.add("ingest-processing")
    if settings.SOAR_WORKER_INTERVAL_SECONDS > 0:
        expected.add("soar-retries")
    if settings.EXPORT_WORKER_INTERVAL_SECONDS > 0:
        expected.add("exports")
    if settings.PROJECTION_TICK_SECONDS > 0:
        expected.add("projection-catchup")
    if settings.ANALYTICS_ROLLUP_INTERVAL_SECONDS > 0:
        expected.add("analytics-rollup")
    if settings.TRAINING_TICK_SECONDS > 0:
        expected.add("ml-training")
    if settings.RETENTION_SWEEP_INTERVAL_SECONDS > 0:
        expected.add("retention")
    tasks: dict[str, asyncio.Task[None]] = app.state.worker_tasks
    detail: dict[str, dict[str, Any]] = {}
    healthy = True
    for name in sorted(expected):
        task = tasks.get(name)
        if task is None:
            detail[name] = {"state": "missing"}
            healthy = False
            continue
        if task.done():
            detail[name] = {"state": "stopped"}
            healthy = False
            continue
        worker_healthy, worker_detail = app.state.worker_health.status(name)
        detail[name] = worker_detail
        healthy = healthy and worker_healthy
    return healthy, detail


# --- Lifespan: soft-connect deps, warm JWKS, sync use_cases, clean shutdown ---
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(debug=settings.DEBUG)

    # Soft-connect: local `uv run forjd` works without Compose up.
    # /ready reports whether Postgres + Redis are actually reachable.
    app.state.dependency_lock = asyncio.Lock()
    app.state.worker_lock = asyncio.Lock()
    app.state.runtime_readiness_lock = asyncio.Lock()
    app.state.runtime_readiness_task: asyncio.Task[dict[str, bool]] | None = None
    app.state.worker_stop = asyncio.Event()
    app.state.worker_tasks: dict[str, asyncio.Task[None]] = {}
    app.state.worker_health = WorkerHealthRegistry()
    app.state.prepared_pool_ids: set[int] = set()
    app.state.verified_worker_contract_pools: dict[int, Any] = {}
    app.state.db_pool = await create_db_pool()
    app.state.redis = await create_redis_client()
    await warm_jwks()

    pool = getattr(app.state, "db_pool", None)
    if pool is not None:
        try:
            await _prepare_pool(app, pool)
        except Exception as exc:  # noqa: BLE001
            # Local boot without Postgres / migrations still allowed; /ready gates traffic.
            logger.warning("startup schema/use_cases sync skipped: %s", exc)
    await _ensure_background_workers(app, pool)

    yield

    app.state.worker_stop.set()
    worker_tasks = list(app.state.worker_tasks.values())
    for worker_task in worker_tasks:
        worker_task.cancel()
    for worker_task in worker_tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task

    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()

    pool = getattr(app.state, "db_pool", None)
    if pool is not None:
        from app.services import exports as export_svc
        from app.services import tenants as tenant_svc

        # Schema readiness is cached per concrete pool; discard that entry
        # before the pool can be closed and its object id reused.
        tenant_svc.reset_secure_schema_cache(pool)
        export_svc.reset_export_schema_cache(pool)
        await pool.close()

    try:
        from app.services.engine import close_engine_clients

        await close_engine_clients()
    except Exception as exc:  # noqa: BLE001
        logger.warning("engine client shutdown: %s", exc)


# --- App + middleware stack ---
# No human docs HTML on this host — community site owns /documentation.
# Machine OpenAPI JSON stays optional behind ENABLE_API_DOCS.
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None,
)

# --- Exception handlers (generic 500 in production) ---
register_exception_handlers(app)

# Sentry (SDK-level, before middleware), Rollbar, then security headers, API key, CORS
configure_sentry()
configure_rollbar(app)
app.add_middleware(
    IngestBodyLimitMiddleware,
    paths=ingest_write_paths(settings.API_V1_STR),
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ApiKeyMiddleware)
app.add_middleware(PublicRateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Auth is Bearer/header based — no cookie sessions; keep credentials off.
    allow_credentials=False,
    # PUT/PATCH/DELETE are part of case, playbook, and credential lifecycle APIs.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
    expose_headers=[
        "Content-Disposition",
        "Link",
        "Location",
        "Retry-After",
        "Server-Timing",
        "X-Request-ID",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "X-Max-Body-Bytes",
    ],
)
app.add_middleware(RequestContextMiddleware)
# Outermost: upgrade cleartext before auth/rate-limit work (Fly X-Forwarded-Proto).
app.add_middleware(HttpsRedirectMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- Root splash (human docs on the community site) ---
_COMMUNITY_DOCS = "https://dataengineeringformachinelearning.com/documentation"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing() -> HTMLResponse:
    """On-brand splash — documentation lives on the community site."""
    return HTMLResponse(content=render_landing())


@app.get("/docs", include_in_schema=False)
@app.get("/redoc", include_in_schema=False)
async def docs_redirect() -> RedirectResponse:
    """Legacy HTML docs → community documentation."""
    return RedirectResponse(url=_COMMUNITY_DOCS, status_code=301)


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
async def robots() -> PlainTextResponse:
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /openapi.json\n"
        "Allow: /api/v1/addons\nSitemap: https://backend.forjd.co/sitemap.xml\n"
    )


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap() -> Response:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://backend.forjd.co/</loc><changefreq>weekly</changefreq></url>
  <url><loc>https://backend.forjd.co/api/v1/addons</loc><changefreq>weekly</changefreq></url>
</urlset>"""
    return Response(content=xml, media_type="application/xml")


# --- Probes (ops only — excluded from public OpenAPI) ---
@app.get("/health", include_in_schema=False)
async def health_check() -> dict[str, str]:
    """Liveness — process is up. Does not check dependencies."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/ready", include_in_schema=False)
async def readiness(request: Request) -> JSONResponse:
    """Readiness — Postgres + Redis (+ optional engine) must respond."""
    checks: dict[str, bool] = {
        "postgres": False,
        "redis": False,
        "runtime_setup": False,
        "worker_contracts": False,
        "workers": False,
    }

    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        # Recover from a database startup race without requiring a process restart.
        lock = request.app.state.dependency_lock
        async with lock:
            pool = getattr(request.app.state, "db_pool", None)
            if pool is None:
                pool = await create_db_pool()
                request.app.state.db_pool = pool
    if pool is not None:
        checks.update(await _runtime_readiness_checks(request.app, pool))

    worker_ok, worker_detail = _worker_health(request.app)
    checks["workers"] = worker_ok

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        # Redis/Dragonfly can race API startup just like Postgres; recover
        # without waiting for a process replacement.
        lock = request.app.state.dependency_lock
        async with lock:
            redis = getattr(request.app.state, "redis", None)
            if redis is None:
                redis = await create_redis_client()
                request.app.state.redis = redis
    if redis is not None:
        try:
            checks["redis"] = bool(await redis.ping())
        except Exception:
            checks["redis"] = False

    if settings.is_production:
        from app.core import object_storage

        # Only require object storage when S3/RustFS credentials are configured.
        # Unconfigured export storage must not take the public API offline.
        if object_storage.is_configured():
            checks["object_storage"] = False
            try:
                checks["object_storage"] = await asyncio.wait_for(
                    asyncio.to_thread(object_storage.probe_bucket),
                    timeout=2.0,
                )
            except Exception:
                checks["object_storage"] = False

    # Engine probe is informational — sealed API stays ready if Postgres/Redis/RLS ok.
    # (HTTP engine may restart independently; Python/PyO3 remain soft-fallbacks.)
    engine_meta: dict[str, Any] | None = None
    if settings.ENGINE_URL.strip():
        from app.services import engine as engine_svc

        try:
            # Engine is an independent worker. Keep its informational probe from
            # delaying the API's dependency readiness response.
            remote = await asyncio.wait_for(engine_svc.remote_version(), timeout=1.0)
        except TimeoutError:
            remote = {"ok": False, "error": "probe timeout"}
        engine_ok = bool(remote and remote.get("service") == "forjd-engine")
        engine_meta = {**(remote or {}), "ok": engine_ok}

    ready = all(checks.values())
    body: dict[str, Any] = {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
        "workers": worker_detail,
    }
    if engine_meta is not None:
        body["engine"] = engine_meta
    if not ready:
        failed = sorted(name for name, ok in checks.items() if not ok)
        logger.warning("ready: not_ready failed_checks=%s", ",".join(failed) or "-")
    return JSONResponse(content=body, status_code=200 if ready else 503)
