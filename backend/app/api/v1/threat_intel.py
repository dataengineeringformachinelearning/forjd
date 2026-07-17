"""Threat intelligence API — feeds, lookup, TAXII ingest, correlate."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.domain import CorrelateRequest, TaxiiIngestRequest, ThreatRefreshRequest
from app.services import playbooks as playbook_svc
from app.services import soc as soc_svc
from app.services import threat_intel as threat_svc
from app.services.correlation import evaluate_correlation_rules

router = APIRouter(prefix="/threat-intel", tags=["threat-intel"])


# --- Platform feed refresh (admin member of any tenant; service path) ---
@router.post("/refresh")
async def refresh_threat_intel(
    request: Request,
    body: ThreatRefreshRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user  # authenticated operator
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    if body.source != "abuse.ch":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unsupported source")
    # Prefer direct async path under uvicorn; Prefect flow is for sync cron workers.
    return await threat_svc.refresh_abuse_ch_platform(pool)


@router.post("/taxii")
async def ingest_taxii(
    request: Request,
    body: TaxiiIngestRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
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
    return {"ok": True, "source": body.source, "count": count}


@router.get("/lookup")
async def lookup_ip(
    request: Request,
    ip: str = Query(..., min_length=7, max_length=64),
    tenant_id: UUID | None = None,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    hits = await threat_svc.lookup_ip(pool, ip_address=ip, tenant_id=tenant_id)
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
    matches = evaluate_correlation_rules(body.context)
    case = None
    if matches:
        case = await soc_svc.open_case_from_context(
            pool,
            tenant_id=body.tenant_id,
            context=body.context,
            actor_id=user.user_id,
        )
    playbook_runs: list[dict[str, Any]] = []
    if body.run_playbooks and matches:
        playbook_runs = await playbook_svc.run_matching_playbooks(
            pool,
            tenant_id=body.tenant_id,
            context=body.context,
        )
    return {
        "ok": True,
        "matches": [
            {
                "rule_id": m.rule_id,
                "title": m.title,
                "severity": m.severity,
                "description": m.description,
            }
            for m in matches
        ],
        "case": case,
        "playbooks": playbook_runs,
    }
