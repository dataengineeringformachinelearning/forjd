"""Aggregate v1 routers (pulse PoC + secure E2EE path)."""

from fastapi import APIRouter

from app.api.v1 import (
    anomaly,
    domain,
    exports,
    ingest,
    playbooks,
    projections,
    pulse,
    replay,
    service_accounts,
    sessions,
    soc,
    stack,
    status,
    tenants,
    threat_intel,
    threat_ml,
    workflows,
)

api_router = APIRouter()

# --- Stack PoC ---
api_router.include_router(pulse.router)
api_router.include_router(stack.router)
api_router.include_router(anomaly.router)

# --- Secure streaming (Auth + E2EE + configurable workflows) ---
api_router.include_router(tenants.router)
api_router.include_router(service_accounts.router)
api_router.include_router(ingest.router)
api_router.include_router(sessions.router)
api_router.include_router(workflows.router)

# --- Projections, replay/DLQ, tenant status pages ---
api_router.include_router(projections.router)
api_router.include_router(replay.router)
api_router.include_router(status.router)

# --- DEML domain extract (threat / SOC / playbooks / exports / threat ML) ---
api_router.include_router(threat_intel.router)
api_router.include_router(soc.router)
api_router.include_router(playbooks.router)
api_router.include_router(exports.router)
api_router.include_router(threat_ml.router)
api_router.include_router(domain.router)
