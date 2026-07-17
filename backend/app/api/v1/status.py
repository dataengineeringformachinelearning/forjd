"""Status pages API — public published pages + JWT-managed ops visibility."""

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


class CreateServiceRequest(BaseModel):
    tenant_id: UUID
    name: str = Field(..., min_length=1, max_length=128)
    status: Literal[
        "operational", "degraded", "partial_outage", "major_outage", "maintenance"
    ] = "operational"
    description: str = ""
    sort_order: int = 0


class CreateIncidentRequest(BaseModel):
    tenant_id: UUID
    title: str = Field(..., min_length=1, max_length=200)
    status: Literal["investigating", "identified", "monitoring", "resolved"] = (
        "investigating"
    )
    severity: Literal["minor", "major", "critical"] = "minor"
    body: str = ""


# --- Member list / create ---
@router.get("/pages")
async def list_pages(
    request: Request,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    pages = await status_svc.list_pages(pool, user=user, tenant_id=tenant_id)
    return {"ok": True, "pages": pages}


@router.post("/pages")
async def create_page(
    request: Request,
    body: CreatePageRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        page = await status_svc.create_page(
            pool,
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


# --- Public published page (no auth) ---
@router.get("/pages/slug/{slug}")
async def public_page(request: Request, slug: str) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    page = await status_svc.get_published_page(pool, slug=slug)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="status page not found")
    return {"ok": True, "page": page}


@router.post("/pages/{page_id}/services")
async def add_service(
    request: Request,
    page_id: UUID,
    body: CreateServiceRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        svc = await status_svc.upsert_service(
            pool,
            user=user,
            tenant_id=body.tenant_id,
            page_id=page_id,
            name=body.name,
            status=body.status,
            description=body.description,
            sort_order=body.sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "service": svc}


@router.post("/pages/{page_id}/incidents")
async def add_incident(
    request: Request,
    page_id: UUID,
    body: CreateIncidentRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        inc = await status_svc.create_incident(
            pool,
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
