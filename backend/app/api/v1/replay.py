"""Event replay + DLQ API (admin/owner or scoped service; metadata-only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import AuthUser, get_current_user
from app.core.deps import require_db_pool
from app.services import replay as replay_svc

router = APIRouter(prefix="/replay", tags=["replay"])


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tenant_id: UUID
    from_time: datetime | None = None
    to_time: datetime | None = None
    from_event_id: UUID | None = None
    workflow_id: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=200, ge=1, le=1000)
    dry_run: bool = False


# --- Replay sealed events through configured workflow ---
@router.post(
    "",
    summary="Replay sealed events through a workflow",
)
async def replay(
    request: Request,
    body: ReplayRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = require_db_pool(request)
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
@router.get(
    "/dlq",
    summary="List dead-letter queue items",
)
async def list_dlq(
    request: Request,
    tenant_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = require_db_pool(request)
    rows = await replay_svc.list_dlq(
        pool,
        user=user,
        tenant_id=tenant_id,
        limit=limit,
    )
    return {"ok": True, "tenant_id": str(tenant_id), "items": rows}


@router.post(
    "/dlq/{dlq_id}/retry",
    summary="Retry one DLQ item",
)
async def retry_dlq(
    request: Request,
    dlq_id: UUID,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = require_db_pool(request)
    try:
        return await replay_svc.retry_dlq_item(pool, user=user, tenant_id=tenant_id, dlq_id=dlq_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
