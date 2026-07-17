"""Export jobs API — Polars batch CSV/JSON/Parquet."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.domain import CreateExportRequest
from app.services import exports as export_svc

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("")
async def list_exports(
    request: Request,
    tenant_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    jobs = await export_svc.list_jobs(pool, user=user, tenant_id=tenant_id, limit=limit)
    return {"ok": True, "jobs": jobs}


@router.post("")
async def create_export(
    request: Request,
    body: CreateExportRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    return await export_svc.create_and_run_export(
        pool,
        user=user,
        tenant_id=body.tenant_id,
        format=body.format,
        source_kind=body.source_kind,
        limit=body.limit,
    )
