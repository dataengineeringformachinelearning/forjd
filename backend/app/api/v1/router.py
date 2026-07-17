"""Aggregate v1 routers (pulse PoC + secure E2EE path)."""

from fastapi import APIRouter

from app.api.v1 import (
    anomaly,
    ingest,
    projections,
    pulse,
    replay,
    sessions,
    stack,
    status,
    tenants,
    workflows,
)

api_router = APIRouter()

# --- Stack PoC ---
api_router.include_router(pulse.router)
api_router.include_router(stack.router)
api_router.include_router(anomaly.router)

# --- Secure streaming (Auth + E2EE + configurable workflows) ---
api_router.include_router(tenants.router)
api_router.include_router(ingest.router)
api_router.include_router(sessions.router)
api_router.include_router(workflows.router)

# --- Projections, replay/DLQ, tenant status pages ---
api_router.include_router(projections.router)
api_router.include_router(replay.router)
api_router.include_router(status.router)
