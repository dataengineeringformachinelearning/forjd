"""Aggregate v1 routers (pulse PoC + secure E2EE path)."""

from fastapi import APIRouter

from app.api.v1 import anomaly, ingest, pulse, sessions, stack, tenants

api_router = APIRouter()

# --- Stack PoC ---
api_router.include_router(pulse.router)
api_router.include_router(stack.router)
api_router.include_router(anomaly.router)

# --- Secure streaming (Auth + E2EE) ---
api_router.include_router(tenants.router)
api_router.include_router(ingest.router)
api_router.include_router(sessions.router)
