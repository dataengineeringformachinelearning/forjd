"""Domain security APIs — scanners, assets, analytics, honeypots, reports, compliance."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.services import analytics as analytics_svc
from app.services import assets as assets_svc
from app.services import compliance as compliance_svc
from app.services import firecrawl as firecrawl_svc
from app.services import honeypot as honeypot_svc
from app.services import lighthouse as lighthouse_svc
from app.services import osint as osint_svc
from app.services import reports as reports_svc
from app.services import security_ingest as security_ingest_svc
from app.services import tenants as tenant_svc
from app.services.ml import sla_model as sla_ml

router = APIRouter(tags=["domain"])


# --- Request models ---
class LighthouseScanRequest(BaseModel):
    tenant_id: UUID
    url: str = Field(..., min_length=8, max_length=2048)


class OsintDomainRequest(BaseModel):
    tenant_id: UUID
    domain: str = Field(..., min_length=3, max_length=255)


class HibpRequest(BaseModel):
    tenant_id: UUID
    email: str = Field(..., min_length=3, max_length=320)


class AhmiaRequest(BaseModel):
    keyword: str = Field(..., min_length=2, max_length=128)


class AssetCreateRequest(BaseModel):
    tenant_id: UUID
    hostname: str = Field(..., min_length=1, max_length=255)
    environment: Literal["production", "staging", "development"] = "production"
    internal_ip: str | None = None
    os_version: str | None = None


class VulnCreateRequest(BaseModel):
    tenant_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    status: Literal["triage", "open", "in_progress", "resolved", "false_positive"] = "triage"
    cve_id: str | None = None
    asset_id: UUID | None = None


class SiteRegisterRequest(BaseModel):
    tenant_id: UUID
    domain: str = Field(..., min_length=3, max_length=255)
    is_verified: bool = True


class SiteEnrichRequest(BaseModel):
    tenant_id: UUID
    site_id: UUID
    url: str | None = None


class AnalyticsAggregateRequest(BaseModel):
    tenant_id: UUID


class HoneypotCreateRequest(BaseModel):
    tenant_id: UUID
    path: str = Field(..., min_length=1, max_length=512)
    trap_type: str = "generic"


class HoneypotHitRequest(BaseModel):
    tenant_id: UUID
    path: str
    source_ip: str | None = None
    method: str = "GET"
    user_agent: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ReportRequest(BaseModel):
    tenant_id: UUID
    title: str = "FORJD Stream Report"
    limit: int = Field(default=500, ge=1, le=1000)


class SecurityAlertRequest(BaseModel):
    tenant_id: UUID
    source: str = Field(..., min_length=1, max_length=128)
    severity: Literal["low", "medium", "high", "critical"] = "high"
    title: str = Field(..., min_length=1, max_length=255)
    ip_address: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class SlaTrainRequest(BaseModel):
    tenant_id: UUID


def _pool(request: Request) -> Any:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    return pool


# --- Lighthouse ---
@router.post("/lighthouse/scan")
async def lighthouse_scan(
    request: Request,
    body: LighthouseScanRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await lighthouse_svc.scan_and_store(
        _pool(request), user=user, tenant_id=body.tenant_id, url=body.url
    )


@router.get("/lighthouse")
async def lighthouse_list(
    request: Request,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    items = await lighthouse_svc.list_scans(_pool(request), user=user, tenant_id=tenant_id)
    return {"ok": True, "scans": items}


# --- OSINT ---
@router.post("/osint/domain")
async def osint_domain(
    request: Request,
    body: OsintDomainRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await osint_svc.scan_and_persist_domain(
        _pool(request), user=user, tenant_id=body.tenant_id, domain=body.domain
    )


@router.post("/osint/hibp")
async def osint_hibp(
    request: Request,
    body: HibpRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    await tenant_svc.require_member(
        _pool(request), tenant_id=body.tenant_id, user_id=user.user_id
    )
    return await osint_svc.check_hibp_breaches(
        _pool(request), account_email=body.email, tenant_id=body.tenant_id
    )


@router.post("/osint/ahmia")
async def osint_ahmia(
    body: AhmiaRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user
    return await osint_svc.search_ahmia(body.keyword)


# --- Assets / vulns ---
@router.get("/assets")
async def list_assets(
    request: Request,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": True,
        "assets": await assets_svc.list_assets(_pool(request), user=user, tenant_id=tenant_id),
    }


@router.post("/assets")
async def create_asset(
    request: Request,
    body: AssetCreateRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    asset = await assets_svc.create_asset(
        _pool(request),
        user=user,
        tenant_id=body.tenant_id,
        hostname=body.hostname,
        environment=body.environment,
        internal_ip=body.internal_ip,
        os_version=body.os_version,
    )
    return {"ok": True, "asset": asset}


@router.get("/vulnerabilities")
async def list_vulns(
    request: Request,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": True,
        "vulnerabilities": await assets_svc.list_vulnerabilities(
            _pool(request), user=user, tenant_id=tenant_id
        ),
    }


@router.post("/vulnerabilities")
async def create_vuln(
    request: Request,
    body: VulnCreateRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    vuln = await assets_svc.create_vulnerability(
        _pool(request),
        user=user,
        tenant_id=body.tenant_id,
        title=body.title,
        description=body.description,
        severity=body.severity,
        status=body.status,
        cve_id=body.cve_id,
        asset_id=body.asset_id,
    )
    return {"ok": True, "vulnerability": vuln}


# --- Firecrawl / tech ---
@router.post("/sites")
async def register_site(
    request: Request,
    body: SiteRegisterRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    site = await firecrawl_svc.register_validated_site(
        _pool(request),
        user=user,
        tenant_id=body.tenant_id,
        domain=body.domain,
        is_verified=body.is_verified,
    )
    return {"ok": True, "site": site}


@router.post("/sites/enrich")
async def enrich_site(
    request: Request,
    body: SiteEnrichRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await firecrawl_svc.enrich_site(
            _pool(request),
            user=user,
            tenant_id=body.tenant_id,
            site_id=body.site_id,
            url=body.url,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except firecrawl_svc.FirecrawlTechnologyError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# --- Analytics ---
@router.post("/analytics/aggregate")
async def analytics_aggregate(
    request: Request,
    body: AnalyticsAggregateRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    await tenant_svc.require_member(
        _pool(request), tenant_id=body.tenant_id, user_id=user.user_id
    )
    return await analytics_svc.aggregate_hour(_pool(request), tenant_id=body.tenant_id)


@router.get("/analytics/overview")
async def analytics_overview(
    request: Request,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await analytics_svc.overview(_pool(request), user=user, tenant_id=tenant_id)


# --- Honeypots ---
@router.post("/honeypots")
async def create_honeypot(
    request: Request,
    body: HoneypotCreateRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        hp = await honeypot_svc.create_honeypot(
            _pool(request),
            user=user,
            tenant_id=body.tenant_id,
            path=body.path,
            trap_type=body.trap_type,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "honeypot": hp}


@router.post("/honeypots/hit")
async def honeypot_hit(
    request: Request,
    body: HoneypotHitRequest,
) -> dict[str, Any]:
    # Unauthenticated decoy hit path (tenant_id required in body; treat as trap).
    hit = await honeypot_svc.log_interaction(
        _pool(request),
        tenant_id=body.tenant_id,
        path=body.path if body.path.startswith("/") else f"/{body.path}",
        source_ip=body.source_ip,
        method=body.method,
        user_agent=body.user_agent,
        payload=body.payload,
    )
    if hit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="honeypot not found")
    return {"ok": True, "interaction": hit}


@router.get("/honeypots/analyze")
async def honeypot_analyze(
    request: Request,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await honeypot_svc.analyze_honeypot_threats(
        _pool(request), user=user, tenant_id=tenant_id
    )


# --- Reports / compliance / SLA / security ingest ---
@router.post("/reports/pdf")
async def report_pdf(
    request: Request,
    body: ReportRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await reports_svc.generate_stream_report(
            _pool(request),
            user=user,
            tenant_id=body.tenant_id,
            title=body.title,
            limit=body.limit,
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/compliance/soc")
async def compliance_soc(request: Request) -> dict[str, Any]:
    return await compliance_svc.build_soc_status(pool_from_request(request))


@router.post("/sla/train")
async def sla_train(
    request: Request,
    body: SlaTrainRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    await tenant_svc.require_member(
        _pool(request),
        tenant_id=body.tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin"}),
    )
    try:
        return await sla_ml.train_tenant_sla(_pool(request), tenant_id=body.tenant_id)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/integrations/security-alert")
async def security_alert(
    request: Request,
    body: SecurityAlertRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await security_ingest_svc.ingest_security_alert(
        _pool(request),
        user=user,
        tenant_id=body.tenant_id,
        source=body.source,
        severity=body.severity,
        title=body.title,
        ip_address=body.ip_address,
        raw=body.raw,
    )


@router.get("/discovered-endpoints")
async def list_discovered(
    request: Request,
    tenant_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = _pool(request)
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    await osint_svc.ensure_osint_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, url, source, is_active, created_at
        FROM discovered_endpoints
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        str(tenant_id),
        limit,
    )
    return {"ok": True, "endpoints": [dict(r) for r in rows]}
