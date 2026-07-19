"""Event replay + DLQ API (admin/owner or scoped service; metadata-only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.services import replay as replay_svc

router = APIRouter(prefix="/replay", tags=["replay"])


class ReplayRequest(BaseModel):
    tenant_id: UUID
    from_time: datetime | None = None
    to_time: datetime | None = None
    from_event_id: UUID | None = None
    workflow_id: str | None = None
    limit: int = Field(default=200, ge=1, le=1000)
    dry_run: bool = False


# --- Replay sealed events through configured workflow ---
@router.post("")
async def replay(
    request: Request,
    body: ReplayRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        return await replay_svc.replay_events(
            pool,
            user=user,
            tenant_id=body.tenant_id,
            from_time=body.from_time,
            to_time=body.to_time,
            from_event_id=body.from_event_id,
            workflow_id=body.workflow_id,
            limit=body.limit,
            dry_run=body.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --- DLQ ---
@router.get("/dlq")
async def list_dlq(
    request: Request,
    tenant_id: UUID,
    limit: int = 50,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    rows = await replay_svc.list_dlq(
        pool,
        user=user,
        tenant_id=tenant_id,
        limit=max(1, min(limit, 200)),
    )
    return {"ok": True, "tenant_id": str(tenant_id), "items": rows}


@router.post("/dlq/{dlq_id}/retry")
async def retry_dlq(
    request: Request,
    dlq_id: UUID,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        return await replay_svc.retry_dlq_item(pool, user=user, tenant_id=tenant_id, dlq_id=dlq_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
