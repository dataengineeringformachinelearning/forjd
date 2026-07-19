"""Headless SIEM API for selectively disclosed normalized security signals."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.siem import CreateSecuritySignalRequest, Severity, SignalCategory
from app.services import siem as siem_svc

router = APIRouter(prefix="/siem", tags=["siem"])


@router.post("/signals")
async def create_security_signal(
    request: Request,
    body: CreateSecuritySignalRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    result = await siem_svc.create_signal(pool, user=user, signal=body)
    return {"ok": True, **result}


@router.get("/signals")
async def list_security_signals(
    request: Request,
    tenant_id: UUID,
    severity: Severity | None = None,
    category: SignalCategory | None = None,
    source: str | None = Query(default=None, min_length=1, max_length=128),
    observed_after: datetime | None = None,
    observed_before: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    for value in (observed_after, observed_before):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="signal time filters must include a timezone",
            )
    signals = await siem_svc.list_signals(
        pool,
        user=user,
        tenant_id=tenant_id,
        severity=severity,
        category=category,
        source=source.lower() if source else None,
        observed_after=observed_after,
        observed_before=observed_before,
        limit=limit,
    )
    return {"ok": True, "signals": signals}
