"""Tenant management (JWT-gated)."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.tenant import TenantCreate
from app.services import tenants as tenant_svc

router = APIRouter(prefix="/tenants", tags=["tenants"])


# --- List memberships for the authenticated user ---
@router.get("")
async def list_tenants(
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        await tenant_svc.ensure_secure_schema(pool)
        items = await tenant_svc.list_tenants_for_user(pool, user_id=user.user_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"tenants unavailable — run sql/003_secure_tenancy.sql ({exc})",
        ) from exc
    return {"ok": True, "tenants": items}


# --- Create tenant + owner membership ---
@router.post("")
async def create_tenant(
    request: Request,
    body: TenantCreate,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        await tenant_svc.ensure_secure_schema(pool)
        tenant = await tenant_svc.create_tenant(
            pool,
            slug=body.slug,
            name=body.name,
            owner_user_id=user.user_id,
            key_directory_id=body.key_directory_id,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="slug already taken") from exc
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "unique" in msg.lower() or "duplicate" in msg.lower():
            raise HTTPException(status.HTTP_409_CONFLICT, detail="slug already taken") from exc
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=msg) from exc
    return {"ok": True, "tenant": tenant}
