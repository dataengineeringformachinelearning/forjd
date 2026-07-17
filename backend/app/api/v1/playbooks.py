"""Security playbooks API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.domain import CreatePlaybookRequest
from app.services import playbooks as playbook_svc

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


@router.get("")
async def list_playbooks(
    request: Request,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    items = await playbook_svc.list_playbooks(pool, user=user, tenant_id=tenant_id)
    return {"ok": True, "playbooks": items}


@router.post("")
async def create_playbook(
    request: Request,
    body: CreatePlaybookRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    item = await playbook_svc.create_playbook(
        pool,
        user=user,
        tenant_id=body.tenant_id,
        name=body.name,
        description=body.description,
        trigger_conditions=body.trigger_conditions,
        actions=[a.model_dump() for a in body.actions],
    )
    return {"ok": True, "playbook": item}
