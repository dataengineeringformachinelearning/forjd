"""Status pages API — public published pages + member/service-managed CRUD."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.services import status as status_svc

router = APIRouter(prefix="/status", tags=["status"])


class CreatePageRequest(BaseModel):
    tenant_id: UUID
    slug: str = Field(..., min_length=2, max_length=64)
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    is_published: bool = False


class UpdatePageRequest(BaseModel):
    tenant_id: UUID
    slug: str | None = Field(default=None, min_length=2, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_published: bool | None = None


class CreateServiceRequest(BaseModel):
    tenant_id: UUID
    name: str = Field(..., min_length=1, max_length=128)
    status: Literal["operational", "degraded", "partial_outage", "major_outage", "maintenance"] = (
        "operational"
    )
    description: str = ""
    probe_url: str | None = None
    sort_order: int = 0


class UpdateServiceRequest(BaseModel):
    tenant_id: UUID
    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: (
        Literal["operational", "degraded", "partial_outage", "major_outage", "maintenance"] | None
    ) = None
    description: str | None = None
    probe_url: str | None = None
    sort_order: int | None = None


class CreateIncidentRequest(BaseModel):
    tenant_id: UUID
    title: str = Field(..., min_length=1, max_length=200)
    status: Literal["investigating", "identified", "monitoring", "resolved"] = "investigating"
    severity: Literal["minor", "major", "critical"] = "minor"
    body: str = ""


class UpdateIncidentRequest(BaseModel):
    tenant_id: UUID
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["investigating", "identified", "monitoring", "resolved"] | None = None
    severity: Literal["minor", "major", "critical"] | None = None
    body: str | None = None


def _pool(request: Request) -> Any:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    return pool


# --- Member list / create ---
@router.get("/pages")
async def list_pages(
    request: Request,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pages = await status_svc.list_pages(_pool(request), user=user, tenant_id=tenant_id)
    return {"ok": True, "pages": pages}


@router.post("/pages")
async def create_page(
    request: Request,
    body: CreatePageRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        page = await status_svc.create_page(
            _pool(request),
            user=user,
            tenant_id=body.tenant_id,
            slug=body.slug,
            title=body.title,
            description=body.description,
            is_published=body.is_published,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "page": page}


@router.patch("/pages/{page_id}")
async def patch_page(
    request: Request,
    page_id: UUID,
    body: UpdatePageRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        page = await status_svc.update_page(
            _pool(request),
            user=user,
            tenant_id=body.tenant_id,
            page_id=page_id,
            slug=body.slug,
            title=body.title,
            description=body.description,
            is_published=body.is_published,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True, "page": page}


@router.delete("/pages/{page_id}")
async def remove_page(
    request: Request,
    page_id: UUID,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        await status_svc.delete_page(
            _pool(request), user=user, tenant_id=tenant_id, page_id=page_id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True}


# --- Public published page (no auth) ---
@router.get("/pages/slug/{slug}")
async def public_page(request: Request, slug: str) -> dict[str, Any]:
    page = await status_svc.get_published_page(_pool(request), slug=slug)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="status page not found")
    return {"ok": True, "page": page}


# --- Services ---
@router.get("/pages/{page_id}/services")
async def list_page_services(
    request: Request,
    page_id: UUID,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        services = await status_svc.list_services(
            _pool(request), user=user, tenant_id=tenant_id, page_id=page_id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True, "services": services}


@router.post("/pages/{page_id}/services")
async def add_service(
    request: Request,
    page_id: UUID,
    body: CreateServiceRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        svc = await status_svc.upsert_service(
            _pool(request),
            user=user,
            tenant_id=body.tenant_id,
            page_id=page_id,
            name=body.name,
            status=body.status,
            description=body.description,
            probe_url=body.probe_url,
            sort_order=body.sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "service": svc}


@router.patch("/services/{service_id}")
async def patch_service(
    request: Request,
    service_id: UUID,
    body: UpdateServiceRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        svc = await status_svc.update_service(
            _pool(request),
            user=user,
            tenant_id=body.tenant_id,
            service_id=service_id,
            name=body.name,
            status=body.status,
            description=body.description,
            probe_url=body.probe_url,
            sort_order=body.sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True, "service": svc}


@router.delete("/services/{service_id}")
async def remove_service(
    request: Request,
    service_id: UUID,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        await status_svc.delete_service(
            _pool(request), user=user, tenant_id=tenant_id, service_id=service_id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True}


# --- Incidents ---
@router.get("/pages/{page_id}/incidents")
async def list_page_incidents(
    request: Request,
    page_id: UUID,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        incidents = await status_svc.list_incidents(
            _pool(request), user=user, tenant_id=tenant_id, page_id=page_id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True, "incidents": incidents}


@router.post("/pages/{page_id}/incidents")
async def add_incident(
    request: Request,
    page_id: UUID,
    body: CreateIncidentRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        inc = await status_svc.create_incident(
            _pool(request),
            user=user,
            tenant_id=body.tenant_id,
            page_id=page_id,
            title=body.title,
            status=body.status,
            severity=body.severity,
            body=body.body,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "incident": inc}


@router.patch("/incidents/{incident_id}")
async def patch_incident(
    request: Request,
    incident_id: UUID,
    body: UpdateIncidentRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        inc = await status_svc.update_incident(
            _pool(request),
            user=user,
            tenant_id=body.tenant_id,
            incident_id=incident_id,
            title=body.title,
            status=body.status,
            severity=body.severity,
            body=body.body,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True, "incident": inc}


@router.delete("/incidents/{incident_id}")
async def remove_incident(
    request: Request,
    incident_id: UUID,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        await status_svc.delete_incident(
            _pool(request), user=user, tenant_id=tenant_id, incident_id=incident_id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True}
