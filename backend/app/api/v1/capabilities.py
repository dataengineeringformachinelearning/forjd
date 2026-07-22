"""Public machine-readable contract for DEML and other headless clients.

The document is derived from the routes mounted on the running application so
it cannot advertise a capability whose required HTTP surface was omitted from
the deployment.  It contains no tenant or deployment secrets and is therefore
safe to use as a pre-authentication compatibility probe.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.core.config import settings
from app.core.ingest_limits import (
    MAX_CIPHERTEXT_BASE64_CHARACTERS,
    MAX_INGEST_BATCH_EVENTS,
    MAX_INGEST_BODY_BYTES,
)

router = APIRouter(tags=["capabilities"])

CONTRACT_VERSION = "1.0"

# A capability is ready only when every route in its minimal contract is
# mounted. Optional aliases are deliberately excluded from these requirements.
_REQUIRED_ROUTES: dict[str, tuple[tuple[str, str], ...]] = {
    "sealed_ingest": (
        ("POST", "/api/v1/ingest"),
        ("POST", "/api/v1/ingest/events:batch"),
        ("GET", "/api/v1/ingest/processing/{batch_id}"),
        ("GET", "/api/v1/ingest/results"),
    ),
    "crypto_sessions": (
        ("POST", "/api/v1/sessions"),
        ("GET", "/api/v1/sessions"),
    ),
    "projections": (
        ("GET", "/api/v1/projections"),
        ("POST", "/api/v1/projections/run"),
    ),
    "replay_dlq": (
        ("POST", "/api/v1/replay"),
        ("GET", "/api/v1/replay/dlq"),
        ("POST", "/api/v1/replay/dlq/{dlq_id}/retry"),
    ),
    "siem": (
        ("POST", "/api/v1/siem/signals"),
        ("GET", "/api/v1/siem/signals"),
        ("GET", "/api/v1/soc/cases"),
        ("PATCH", "/api/v1/soc/cases/{case_id}"),
    ),
    "soar": (
        ("GET", "/api/v1/playbooks"),
        ("POST", "/api/v1/playbooks/{playbook_id}/execute"),
        ("GET", "/api/v1/playbooks/runs"),
        (
            "POST",
            "/api/v1/playbooks/runs/{run_id}/actions/{action_result_id}/ack",
        ),
        (
            "POST",
            "/api/v1/playbooks/runs/{run_id}/actions/{action_result_id}/retry",
        ),
    ),
    "threat_intelligence": (
        ("GET", "/api/v1/threat-intel/lookup"),
        ("POST", "/api/v1/threat-intel/correlate"),
    ),
    "exports": (
        ("GET", "/api/v1/exports"),
        ("POST", "/api/v1/exports"),
        ("GET", "/api/v1/exports/{job_id}"),
        ("DELETE", "/api/v1/exports/{job_id}"),
        ("GET", "/api/v1/exports/{job_id}/download"),
    ),
    "report_documents": (
        ("POST", "/api/v1/reports/documents"),
        ("GET", "/api/v1/reports/documents"),
    ),
    "analytics": (
        ("GET", "/api/v1/analytics/overview"),
        ("POST", "/api/v1/analytics/aggregate"),
    ),
    "ml": (
        ("GET", "/api/v1/ml/models"),
        ("GET", "/api/v1/ml/scores"),
    ),
    "status_pages": (
        ("GET", "/api/v1/status/pages"),
        ("POST", "/api/v1/status/pages"),
        ("GET", "/api/v1/status/pages/{page_id}/services"),
    ),
    "tenant_erasure": (("POST", "/api/v1/tenants/{tenant_id}/erase"),),
}


def _mounted_routes(openapi: dict[str, Any]) -> set[tuple[str, str]]:
    mounted: set[tuple[str, str]] = set()
    paths = openapi.get("paths")
    if not isinstance(paths, dict):
        return mounted
    for path, operations in paths.items():
        if not isinstance(path, str) or not isinstance(operations, dict):
            continue
        for method in operations:
            normalized = str(method).upper()
            if normalized in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                mounted.add((normalized, path))
    return mounted


def build_capability_document(openapi: dict[str, Any]) -> dict[str, Any]:
    """Build the authoritative contract document for the mounted application."""
    mounted = _mounted_routes(openapi)
    capabilities: dict[str, dict[str, Any]] = {}
    for name, required in _REQUIRED_ROUTES.items():
        missing = [f"{method} {path}" for method, path in required if (method, path) not in mounted]
        capabilities[name] = {
            "available": not missing,
            "endpoints": [f"{method} {path}" for method, path in required],
        }
        if missing:
            capabilities[name]["missing"] = missing

    return {
        "contract_version": CONTRACT_VERSION,
        "service": settings.PROJECT_NAME,
        "service_version": settings.PROJECT_VERSION,
        "authentication": {
            "service_tokens": True,
            "service_token_prefix": "fjsvc_",
            "tenant_bound": True,
            "scoped": True,
            "human_identity": "supabase_jwt",
        },
        "capabilities": capabilities,
        "limits": {
            "ingest_batch_events": MAX_INGEST_BATCH_EVENTS,
            "ingest_request_bytes": MAX_INGEST_BODY_BYTES,
            "ciphertext_base64_characters": MAX_CIPHERTEXT_BASE64_CHARACTERS,
            "max_page_size": 100,
            "rate_limit_headers": True,
        },
        "reliability": {
            "request_id": True,
            "idempotent_ingest": True,
            "durable_ingest_processing": True,
            "processing_status_lookup": True,
            "durable_replay_dlq": True,
            "durable_soar_runs": True,
            "durable_soar_retries": True,
            "durable_exports": True,
            "supervised_workers": True,
            "readiness_path": "/ready",
            # Acceptance and its recovery receipt commit atomically. The API
            # still attempts processing synchronously; the worker is recovery,
            # not a promised 202/deferred-ingest contract.
            "ingest_processing_mode": "synchronous",
            "async_processing_available": False,
        },
    }


@router.get("/capabilities")
async def capabilities(request: Request) -> dict[str, Any]:
    """Return the public headless integration contract and mounted features."""
    return build_capability_document(request.app.openapi())
