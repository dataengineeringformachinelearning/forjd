"""Durable projections API — live read models from sealed metadata.

Primary consumer surface for subprocessors (any SaaS):
  GET  /api/v1/projections?tenant_id=&since=…     — poll live scores
  GET  /api/v1/projections/checkpoints            — watermark
  POST /api/v1/projections/run                    — advance from sealed meta

Auth: Supabase user JWT (tenant member) or tenant-bound ``fjsvc_…`` service
token with ``projections:read`` / ``projections:run``. Never partner end-user tokens.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import AuthUser, get_current_user
from app.core.deps import parse_iso_cursor, require_db_pool
from app.services import projections as proj_svc

router = APIRouter(prefix="/projections", tags=["projections"])


class ProjectRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tenant_id: UUID
    workflow_id: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=200, ge=1, le=1000)


# --- List durable projection rows ---
@router.get(
    "",
    summary="Poll durable projection feed",
    description=(
        "Live projection feed for SaaS consumers. Partner BFFs may bridge this "
        "cursor poll into SSE for browsers that must not hold fjsvc_ tokens."
    ),
)
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
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Live projection feed for SaaS consumers (poll or Realtime-subscribe)."""
    pool = require_db_pool(request)
    rows = await proj_svc.list_projections(
        pool,
        user=user,
        tenant_id=tenant_id,
        projection_name=name,
        workflow_id=workflow_id,
        since=parse_iso_cursor(since),
        after_id=after_id,
        limit=limit,
    )
    return {"ok": True, "tenant_id": str(tenant_id), "projections": rows}


# --- Checkpoints ---
@router.get(
    "/checkpoints",
    summary="Get projection checkpoint watermark",
)
async def get_checkpoint(
    request: Request,
    tenant_id: UUID,
    projection_name: str = "sealed.default",
    workflow_id: str = "",
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = require_db_pool(request)
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
@router.post(
    "/run",
    summary="Advance projections from sealed metadata",
)
async def run_projection(
    request: Request,
    body: ProjectRunRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = require_db_pool(request)
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
