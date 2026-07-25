"""Manage tenant-scoped service accounts (enterprise user JWT only).

Subprocessors like partner SaaS call ingest/projections with the minted token —
they never manage keys with that same token.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request, require_user_principal
from app.core.http_errors import (
    GENERIC_REQUEST_FAILED,
    client_safe_detail,
    intentional_detail,
)
from app.models.service_account import ServiceAccountCreate
from app.services import service_accounts as svc

router = APIRouter(prefix="/service-accounts", tags=["service-accounts"])
logger = logging.getLogger("forjd.api.service_accounts")


# --- Create (returns opaque token once; omit mint from public OpenAPI) ---
@router.post("", include_in_schema=False)
async def create_service_account(
    request: Request,
    body: ServiceAccountCreate,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    require_user_principal(user)
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        created = await svc.create_service_account(
            pool,
            user=user,
            tenant_id=body.tenant_id,
            name=body.name,
            subprocessor=body.subprocessor,
            scopes=body.scopes,
            include_tenant_erase=body.include_tenant_erase,
            auth_user_id=body.auth_user_id,
            mint_opaque_token=body.mint_opaque_token,
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=intentional_detail(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("service account create failed")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=client_safe_detail(exc, fallback=GENERIC_REQUEST_FAILED),
        ) from exc
    return {"ok": True, "service_account": created}


# --- List (never includes key material) ---
@router.get("")
async def list_service_accounts(
    request: Request,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    require_user_principal(user)
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    items = await svc.list_service_accounts(pool, user=user, tenant_id=tenant_id)
    return {"ok": True, "tenant_id": str(tenant_id), "service_accounts": items}


# --- Revoke (clears key_hash; JWT binding marked inactive) ---
@router.delete("/{service_account_id}")
async def revoke_service_account(
    request: Request,
    service_account_id: UUID,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    require_user_principal(user)
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    revoked = await svc.revoke_service_account(
        pool,
        user=user,
        tenant_id=tenant_id,
        service_account_id=service_account_id,
    )
    return {"ok": True, "service_account": revoked}
