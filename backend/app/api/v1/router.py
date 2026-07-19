"""Aggregate v1 routers for the universal secure streaming API.

Core (use these from any SaaS / subprocessor):
  tenants, service-accounts, sessions, ingest, workflows, projections, replay

Optional domain APIs (threat/SOC/…) are not required for sealed streaming.
Partner apps call the core as a subprocessor with a tenant ``fjsvc_``
token — see ``backend/docs/AUTH.md``.
"""

from fastapi import APIRouter

from app.api.v1 import (
    addons,
    capabilities,
    domain,
    exports,
    ingest,
    ml,
    playbooks,
    projections,
    replay,
    reports,
    service_accounts,
    sessions,
    siem,
    soc,
    status,
    tenants,
    threat_intel,
    threat_ml,
    workflows,
)

api_router = APIRouter()

# --- Public headless capabilities probe ---
api_router.include_router(capabilities.router)

# --- Universal secure streaming (Auth + E2EE + YAML workflows) ---
# Subprocessors (partner SaaS): service-accounts → sessions → ingest → projections.
api_router.include_router(tenants.router)
api_router.include_router(service_accounts.router)
api_router.include_router(ingest.router)
api_router.include_router(sessions.router)
api_router.include_router(workflows.router)

# --- Projections, replay/DLQ, tenant status pages, report documents ---
api_router.include_router(projections.router)
api_router.include_router(replay.router)
api_router.include_router(status.router)
api_router.include_router(reports.router)

# --- Optional domain extract (not required for sealed streaming core) ---
api_router.include_router(threat_intel.router)
api_router.include_router(siem.router)
api_router.include_router(soc.router)
api_router.include_router(playbooks.router)
api_router.include_router(exports.router)
api_router.include_router(threat_ml.router)
api_router.include_router(ml.router)
api_router.include_router(domain.router)

# --- Add-on catalog (optional integrations; disabled by default) ---
api_router.include_router(addons.router)
