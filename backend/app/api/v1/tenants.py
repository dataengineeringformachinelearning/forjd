"""Tenant management (JWT-gated) + durable erase for partner deletion."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.auth import AuthUser, get_current_user, pool_from_request, require_user_principal
from app.models.tenant import TenantCreate
from app.services import tenant_erase as erase_svc
from app.services import tenants as tenant_svc

router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantEraseBody(BaseModel):
    """Confirm erase — must match path tenant_id (fail closed)."""

    confirm_tenant_id: UUID = Field(..., description="Must equal path tenant_id")


# --- List memberships for the authenticated user ---
@router.get("")
async def list_tenants(
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    # Service principals are bound to exactly one tenant (no membership listing).
    if user.is_service:
        return {
            "ok": True,
            "tenants": [
                {
                    "id": user.tenant_id,
                    "role": "service",
                    "subprocessor": user.subprocessor or "",
                    "scopes": sorted(user.scopes),
                }
            ],
        }
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
    require_user_principal(user)
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


# --- Durable erase (partner account deletion / GDPR) ---
@router.post("/{tenant_id}/erase")
async def erase_tenant(
    request: Request,
    tenant_id: UUID,
    body: TenantEraseBody,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Idempotent tenant wipe + revoke all ``fjsvc_`` credentials for the tenant.

    Allowed for human owner/admin **or** a service principal with ``tenants:erase``
    bound to this tenant. Confirmation body must match the path id.
    """
    if body.confirm_tenant_id != tenant_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="confirm_tenant_id must match path tenant_id",
        )
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        await tenant_svc.ensure_secure_schema(pool)
        return await erase_svc.erase_tenant(pool, principal=user, tenant_id=tenant_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"tenant erase failed: {exc}",
        ) from exc
