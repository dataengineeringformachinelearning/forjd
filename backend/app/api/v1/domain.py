"""Domain security APIs — scanners, assets, analytics, honeypots, reports, compliance."""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.domain import UpdateVulnerabilityRequest
from app.models.siem import validate_signal_metadata
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

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("invalid email")
        local, _, domain = normalized.partition("@")
        if not local or "." not in domain:
            raise ValueError("invalid email")
        return normalized


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
    description: str = Field(default="", max_length=4096)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    status: Literal["triage", "open", "in_progress", "resolved", "false_positive"] = "triage"
    cve_id: str | None = Field(default=None, max_length=64)
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
    path: str = Field(..., min_length=1, max_length=512)
    source_ip: str | None = Field(default=None, max_length=128)
    method: str = Field(default="GET", max_length=16)
    user_agent: str | None = Field(default=None, max_length=512)
    # Cap trap body — unauthenticated decoy must not accept unbounded JSON.
    payload: dict[str, Any] = Field(default_factory=dict, max_length=32)

    @field_validator("payload")
    @classmethod
    def _cap_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(str(value)) > 4096:
            raise ValueError("payload too large")
        return value


class ReportRequest(BaseModel):
    tenant_id: UUID
    title: str = "FORJD Stream Report"
    limit: int = Field(default=500, ge=1, le=1000)


class SecurityAlertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tenant_id: UUID
    client_alert_id: str = Field(
        ...,
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    observed_at: datetime
    source: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    severity: Literal["low", "medium", "high", "critical"] = "high"
    title: str = Field(..., min_length=1, max_length=255)
    ip_address: str | None = Field(default=None, max_length=64)
    raw: dict[str, Any] = Field(default_factory=dict, max_length=32)

    @field_validator("raw")
    @classmethod
    def _safe_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        # Legacy field name retained for compatibility; contents are normalized
        # metadata only and are never persisted as a raw payload.
        return validate_signal_metadata(value)

    @field_validator("ip_address")
    @classmethod
    def _valid_ip(cls, value: str | None) -> str | None:
        return str(ipaddress.ip_address(value)) if value else None

    @field_validator("observed_at")
    @classmethod
    def _observed_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value.astimezone(UTC)


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
    # Persist path writes threat_intelligence — service principals need threat-intel:write.
    await tenant_svc.require_tenant_access(
        _pool(request),
        principal=user,
        tenant_id=body.tenant_id,
        required_scopes=frozenset({"threat-intel:write"}),
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


@router.patch("/vulnerabilities/{vulnerability_id}")
async def update_vuln(
    request: Request,
    vulnerability_id: UUID,
    body: UpdateVulnerabilityRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    vulnerability = await assets_svc.update_vulnerability(
        _pool(request),
        user=user,
        tenant_id=body.tenant_id,
        vulnerability_id=vulnerability_id,
        updates=body.model_dump(exclude={"tenant_id"}, exclude_unset=True),
    )
    return {"ok": True, "vulnerability": vulnerability}


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
    # Rollup write — opt-in scope (not in default mint); overview uses analytics:read.
    await tenant_svc.require_tenant_access(
        _pool(request),
        principal=user,
        tenant_id=body.tenant_id,
        required_scopes=frozenset({"analytics:write"}),
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
    # Unauthenticated decoy hit — always ok to avoid honeypot/tenant enumeration.
    await honeypot_svc.log_interaction(
        _pool(request),
        tenant_id=body.tenant_id,
        path=body.path if body.path.startswith("/") else f"/{body.path}",
        source_ip=body.source_ip,
        method=body.method,
        user_agent=body.user_agent,
        payload=body.payload,
    )
    return {"ok": True}


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
async def compliance_soc(
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Authenticated SOC criteria (static — no cross-tenant DB signals)."""
    del user
    return await compliance_svc.build_soc_status(pool_from_request(request))


@router.post("/sla/train")
async def sla_train(
    request: Request,
    body: SlaTrainRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        _pool(request),
        principal=user,
        tenant_id=body.tenant_id,
        min_roles=frozenset({"owner", "admin"}),
        required_scopes=frozenset({"ml:write"}),
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
        client_alert_id=body.client_alert_id,
        observed_at=body.observed_at,
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
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"threat-intel:read"}),
    )
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
