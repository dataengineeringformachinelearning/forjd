"""Tenant-scoped threat model train/score ."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.core.http_errors import client_safe_detail
from app.models.domain import ThreatScoreRequest, ThreatTrainRequest
from app.services import tenants as tenant_svc
from app.services.ml import threat_model as threat_ml

# Internal threat train/score — omit from public OpenAPI (runtime auth still required).
router = APIRouter(prefix="/threat-ml", tags=["threat-ml"], include_in_schema=False)


@router.post("/train")
async def train_threat(
    request: Request,
    body: ThreatTrainRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    await tenant_svc.require_member(
        pool,
        tenant_id=body.tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin"}),
    )
    try:
        return await threat_ml.train_threat_model(
            pool, tenant_id=body.tenant_id, epochs=body.epochs
        )
    except RuntimeError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=client_safe_detail(exc),
        ) from exc


@router.post("/score")
async def score_threat(
    request: Request,
    body: ThreatScoreRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    await tenant_svc.require_member(pool, tenant_id=body.tenant_id, user_id=user.user_id)
    try:
        return await threat_ml.score_threat_model(pool, tenant_id=body.tenant_id)
    except RuntimeError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=client_safe_detail(exc),
        ) from exc
