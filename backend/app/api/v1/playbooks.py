"""Security playbooks API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.domain import (
    AcknowledgePlaybookActionRequest,
    CreatePlaybookRequest,
    ExecutePlaybookRequest,
    RetryPlaybookActionRequest,
    UpdatePlaybookRequest,
)
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


@router.patch("/{playbook_id}")
async def update_playbook(
    request: Request,
    playbook_id: UUID,
    body: UpdatePlaybookRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    item = await playbook_svc.update_playbook(
        pool,
        user=user,
        tenant_id=body.tenant_id,
        playbook_id=playbook_id,
        updates=body.model_dump(exclude={"tenant_id"}, exclude_unset=True),
    )
    return {"ok": True, "playbook": item}


@router.post("/{playbook_id}/execute")
async def execute_playbook(
    request: Request,
    playbook_id: UUID,
    body: ExecutePlaybookRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    run = await playbook_svc.execute_playbook(
        pool,
        user=user,
        tenant_id=body.tenant_id,
        playbook_id=playbook_id,
        idempotency_key=body.idempotency_key,
        context=body.context,
    )
    return {"ok": True, "run": run}


@router.get("/runs")
async def list_playbook_runs(
    request: Request,
    tenant_id: UUID,
    playbook_id: UUID | None = None,
    source_signal_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    runs = await playbook_svc.list_runs(
        pool,
        user=user,
        tenant_id=tenant_id,
        playbook_id=playbook_id,
        source_signal_id=source_signal_id,
        limit=limit,
    )
    return {"ok": True, "runs": runs}


@router.post("/runs/{run_id}/actions/{action_result_id}/ack")
async def acknowledge_playbook_action(
    request: Request,
    run_id: UUID,
    action_result_id: UUID,
    body: AcknowledgePlaybookActionRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    run = await playbook_svc.acknowledge_action(
        pool,
        user=user,
        tenant_id=body.tenant_id,
        run_id=run_id,
        action_result_id=action_result_id,
        succeeded=body.succeeded,
        external_reference=body.external_reference,
        metadata=body.metadata,
    )
    return {"ok": True, "run": run}


@router.post(
    "/runs/{run_id}/actions/{action_result_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_playbook_action(
    request: Request,
    run_id: UUID,
    action_result_id: UUID,
    body: RetryPlaybookActionRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    run = await playbook_svc.retry_action(
        pool,
        user=user,
        tenant_id=body.tenant_id,
        run_id=run_id,
        action_result_id=action_result_id,
    )
    return {"ok": True, "queued": True, "run": run}
