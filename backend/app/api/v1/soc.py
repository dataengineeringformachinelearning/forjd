"""SOC case management API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.domain import CreateCaseRequest
from app.services import soc as soc_svc

router = APIRouter(prefix="/soc", tags=["soc"])


@router.get("/cases")
async def list_cases(
    request: Request,
    tenant_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    cases = await soc_svc.list_cases(pool, user=user, tenant_id=tenant_id, limit=limit)
    return {"ok": True, "cases": cases}


@router.post("/cases")
async def create_case(
    request: Request,
    body: CreateCaseRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    case = await soc_svc.create_case(
        pool,
        user=user,
        tenant_id=body.tenant_id,
        title=body.title,
        description=body.description,
        severity=body.severity,
        metadata=body.metadata,
    )
    return {"ok": True, "case": case}
