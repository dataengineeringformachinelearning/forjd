"""Threat intelligence API — feeds, lookup, TAXII ingest, correlate."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.domain import CorrelateRequest, TaxiiIngestRequest, ThreatRefreshRequest
from app.services import audit
from app.services import playbooks as playbook_svc
from app.services import soc as soc_svc
from app.services import tenants as tenant_svc
from app.services import threat_intel as threat_svc
from app.services.correlation import evaluate_correlation_rules

router = APIRouter(prefix="/threat-intel", tags=["threat-intel"])


# --- Platform feed refresh (explicit human platform admin only) ---
@router.post("/refresh")
async def refresh_threat_intel(
    request: Request,
    body: ThreatRefreshRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    threat_svc.require_platform_admin(user)
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    if body.source != "abuse.ch":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unsupported source")
    await audit.record_required(
        pool,
        action="threat_intel.platform_refresh_attempt",
        actor_user_id=user.actor_id,
        resource_type="threat_feed",
        resource_id=body.source,
        details={"source": body.source},
    )
    # Prefer direct async path under uvicorn; Prefect flow is for sync cron workers.
    result = await threat_svc.refresh_abuse_ch_platform(pool)
    await audit.record_required(
        pool,
        action="threat_intel.platform_refresh",
        actor_user_id=user.actor_id,
        resource_type="threat_feed",
        resource_id=body.source,
        details={"source": body.source, "count": result.get("count", 0)},
    )
    return result


@router.post("/taxii")
async def ingest_taxii(
    request: Request,
    body: TaxiiIngestRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    if body.is_platform:
        threat_svc.require_platform_admin(user)
    else:
        assert body.tenant_id is not None
        await tenant_svc.require_tenant_access(
            pool,
            principal=user,
            tenant_id=body.tenant_id,
            min_roles=frozenset({"owner", "admin"}),
            required_scopes=frozenset({"threat-intel:write"}),
        )
    await audit.record_required(
        pool,
        action="threat_intel.taxii_ingest_attempt",
        actor_user_id=user.actor_id,
        tenant_id=body.tenant_id,
        resource_type="threat_feed",
        resource_id=body.source,
        details={"scope": "platform" if body.is_platform else "tenant"},
    )
    try:
        indicators = await threat_svc.fetch_taxii_collection(
            body.collection_url,
            username=body.username,
            password=body.password,
        )
        count = await threat_svc.ingest_taxii_indicators(
            pool,
            source=body.source,
            indicators=indicators,
            tenant_id=body.tenant_id,
            is_platform=body.is_platform,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    await audit.record_required(
        pool,
        action="threat_intel.taxii_ingest",
        actor_user_id=user.actor_id,
        tenant_id=body.tenant_id,
        resource_type="threat_feed",
        resource_id=body.source,
        details={
            "source": body.source,
            "count": count,
            "scope": "platform" if body.is_platform else "tenant",
        },
    )
    return {"ok": True, "source": body.source, "count": count}


@router.get("/lookup")
async def lookup_ip(
    request: Request,
    ip: str = Query(..., min_length=7, max_length=64),
    tenant_id: UUID | None = None,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    effective_tenant = tenant_id
    if user.is_service and effective_tenant is None:
        if not user.tenant_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="service tenant binding missing")
        effective_tenant = UUID(user.tenant_id)
    hits = await threat_svc.lookup_ip(
        pool,
        user=user,
        ip_address=ip,
        tenant_id=effective_tenant,
    )
    return {"ok": True, "ip": ip, "hits": hits}


@router.get("")
async def list_threat_intel(
    request: Request,
    tenant_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    items = await threat_svc.list_recent(pool, user=user, tenant_id=tenant_id, limit=limit)
    return {"ok": True, "items": items}


@router.post("/correlate")
async def correlate(
    request: Request,
    body: CorrelateRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=body.tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"siem:write"}),
    )
    # Correlation may disclose or create a case even when the current rule set
    # differs from the one that completed an idempotent request. Authorize the
    # operation, not today's match result.
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=body.tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"cases:write"}),
    )
    if body.run_playbooks:
        await tenant_svc.require_tenant_access(
            pool,
            principal=user,
            tenant_id=body.tenant_id,
            min_roles=frozenset({"owner", "admin", "member"}),
            required_scopes=frozenset({"playbooks:execute"}),
        )
    canonical = json.dumps(
        {"context": body.context, "run_playbooks": body.run_playbooks},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    request_sha256 = hashlib.sha256(canonical.encode()).hexdigest()
    correlation_key = body.idempotency_key or f"correlate:{request_sha256[:48]}"
    await audit.record_required(
        pool,
        action="siem.correlate_attempt",
        actor_user_id=user.actor_id,
        tenant_id=body.tenant_id,
        resource_type="correlation",
        resource_id=correlation_key,
        details={"run_playbooks": body.run_playbooks},
    )
    receipt_id, receipt_created = await threat_svc.claim_correlation_receipt(
        pool,
        tenant_id=body.tenant_id,
        idempotency_key=correlation_key,
        request_sha256=request_sha256,
        actor_id=user.user_id,
    )
    receipt_state = await threat_svc.get_correlation_receipt_state(
        pool,
        tenant_id=body.tenant_id,
        receipt_id=receipt_id,
    )
    if receipt_state is None:
        raise RuntimeError("correlation receipt could not be resolved")
    if not receipt_created and receipt_state["status"] == "completed":
        return {
            "ok": True,
            "duplicate": True,
            "correlation_receipt_id": str(receipt_id),
            **_correlation_result_snapshot(receipt_state["result_snapshot"]),
        }

    matches = evaluate_correlation_rules(body.context)
    case = None
    if matches:
        case = await soc_svc.open_case_from_context(
            pool,
            user=user,
            tenant_id=body.tenant_id,
            context=body.context,
            source_correlation_id=receipt_id,
        )
    playbook_runs: list[dict[str, Any]] = []
    if body.run_playbooks and matches:
        playbook_runs = await playbook_svc.run_matching_playbooks(
            pool,
            user=user,
            tenant_id=body.tenant_id,
            context=body.context,
            idempotency_prefix=f"correlation:{receipt_id}",
            trigger_source="correlation",
        )
    result_snapshot = jsonable_encoder(
        {
            "matches": [
                {
                    "rule_id": match.rule_id,
                    "title": match.title,
                    "severity": match.severity,
                    "description": match.description,
                }
                for match in matches
            ],
            "case": case,
            "playbooks": playbook_runs,
        }
    )
    completed = await threat_svc.complete_correlation_receipt(
        pool,
        tenant_id=body.tenant_id,
        receipt_id=receipt_id,
        match_count=len(matches),
        case_id=UUID(case["id"]) if case is not None else None,
        playbook_run_count=len(playbook_runs),
        result_snapshot=result_snapshot,
        actor_id=user.actor_id,
    )
    if not completed:
        completed_state = await threat_svc.get_correlation_receipt_state(
            pool,
            tenant_id=body.tenant_id,
            receipt_id=receipt_id,
        )
        if completed_state is None or completed_state["status"] != "completed":
            raise RuntimeError("correlation receipt could not be completed")
        result_snapshot = _correlation_result_snapshot(completed_state["result_snapshot"])
    return {
        "ok": True,
        "duplicate": not receipt_created,
        "correlation_receipt_id": str(receipt_id),
        **result_snapshot,
    }


def _correlation_result_snapshot(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    if not isinstance(value, dict):
        value = {}
    matches = value.get("matches")
    case = value.get("case")
    playbooks = value.get("playbooks")
    return {
        "matches": [item for item in matches if isinstance(item, dict)]
        if isinstance(matches, list)
        else [],
        "case": case if isinstance(case, dict) else None,
        "playbooks": [item for item in playbooks if isinstance(item, dict)]
        if isinstance(playbooks, list)
        else [],
    }
