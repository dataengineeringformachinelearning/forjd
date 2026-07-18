"""Aggregate v1 routers (pulse PoC + secure E2EE path).

Universal streaming core (use these from any SaaS / subprocessor):
  tenants, service-accounts, sessions, ingest, workflows, projections, replay

Optional domain APIs (threat/SOC/…) are not required for sealed streaming.
Partner apps call the core as a subprocessor with a tenant ``fjsvc_``
token — see ``backend/docs/AUTH.md``.
"""

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

# --- Universal secure streaming (Auth + E2EE + YAML workflows) ---
# Subprocessors (partner SaaS): service-accounts → sessions → ingest → projections.
api_router.include_router(tenants.router)
api_router.include_router(service_accounts.router)
api_router.include_router(ingest.router)
api_router.include_router(sessions.router)
api_router.include_router(workflows.router)

# --- Projections, replay/DLQ, tenant status pages ---
api_router.include_router(projections.router)
api_router.include_router(replay.router)
api_router.include_router(status.router)

# --- Optional domain extract (not required for sealed streaming core) ---
api_router.include_router(threat_intel.router)
api_router.include_router(soc.router)
api_router.include_router(playbooks.router)
api_router.include_router(exports.router)
api_router.include_router(threat_ml.router)
api_router.include_router(domain.router)
