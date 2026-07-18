"""Durable projections API — live read models from sealed metadata.

Primary consumer surface for subprocessors (any SaaS):
  GET  /api/v1/projections?tenant_id=&since=…     — poll live scores
  GET  /api/v1/projections/checkpoints            — watermark
  POST /api/v1/projections/run                    — advance from sealed meta

Auth: Supabase user JWT (tenant member) or tenant-bound ``fjsvc_…`` service
token with ``projections:read`` / ``projections:run``. Never partner end-user tokens.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.services import projections as proj_svc

router = APIRouter(prefix="/projections", tags=["projections"])


class ProjectRunRequest(BaseModel):
    tenant_id: UUID
    workflow_id: str | None = None
    limit: int = Field(default=200, ge=1, le=1000)


# --- Parse ISO cursor for live polling ---
def _parse_since(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="since must be an ISO-8601 timestamp",
        ) from exc


# --- List durable projection rows ---
@router.get("")
async def list_projections(
    request: Request,
    tenant_id: UUID,
    name: str | None = None,
    workflow_id: str | None = None,
    since: str | None = Query(
        default=None,
        description="ISO-8601 cursor — return rows with created_at > since (ascending)",
    ),
    after_id: UUID | None = Query(
        default=None,
        description="Keyset cursor — return rows after this stream_results.id",
    ),
    limit: int = 50,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Live projection feed for SaaS consumers (poll or Realtime-subscribe)."""
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    rows = await proj_svc.list_projections(
        pool,
        user=user,
        tenant_id=tenant_id,
        projection_name=name,
        workflow_id=workflow_id,
        since=_parse_since(since),
        after_id=after_id,
        limit=max(1, min(limit, 200)),
    )
    return {"ok": True, "tenant_id": str(tenant_id), "projections": rows}


# --- Checkpoints ---
@router.get("/checkpoints")
async def get_checkpoint(
    request: Request,
    tenant_id: UUID,
    projection_name: str = "sealed.default",
    workflow_id: str = "",
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    from app.services import tenants as tenant_svc

    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"projections:read"}),
    )
    ckpt = await proj_svc.get_checkpoint(
        pool,
        tenant_id=tenant_id,
        projection_name=projection_name,
        workflow_id=workflow_id,
    )
    return {"ok": True, "checkpoint": ckpt}


# --- Advance projections from watermark ---
@router.post("/run")
async def run_projection(
    request: Request,
    body: ProjectRunRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        return await proj_svc.run_projection(
            pool,
            user=user,
            tenant_id=body.tenant_id,
            workflow_id=body.workflow_id,
            limit=body.limit,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
