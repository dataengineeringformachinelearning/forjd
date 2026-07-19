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


@router.post("", status_code=status.HTTP_202_ACCEPTED)
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
        idempotency_key=body.idempotency_key,
        format=body.format,
        source_kind=body.source_kind,
        limit=body.limit,
        days=body.days,
        site_url=body.site_url,
    )


@router.get("/{job_id}")
async def get_export(
    request: Request,
    job_id: UUID,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    job = await export_svc.get_job(pool, user=user, tenant_id=tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="export job not found")
    return {"ok": True, "job": job}


@router.get("/{job_id}/download")
async def download_export(
    request: Request,
    job_id: UUID,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    return await export_svc.create_download(
        pool,
        user=user,
        tenant_id=tenant_id,
        job_id=job_id,
    )
