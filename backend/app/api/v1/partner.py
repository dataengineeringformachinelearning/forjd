"""Partner bootstrap APIs — DEML provisions tenants without end-user FORJD access."""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.auth import pool_from_request
from app.core.config import settings
from app.services import partner_provision as provision_svc

router = APIRouter(prefix="/partner", tags=["partner"])
logger = logging.getLogger("forjd.api.partner")


class PartnerProvisionBody(BaseModel):
    external_ref: str = Field(..., min_length=4, max_length=128)
    partner: str = Field(default="deml", max_length=64)
    slug: str | None = Field(default=None, max_length=63)
    name: str | None = Field(default=None, max_length=128)
    include_tenant_erase: bool = True
    remint_if_exists: bool = False


def _require_provision_token(authorization: str | None) -> None:
    expected = (settings.FORJD_PROVISION_TOKEN or "").strip()
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="partner provisioning is not configured",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing provision token")
    provided = authorization[7:].strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid provision token")


@router.post("/provision")
async def provision_partner_tenant(
    request: Request,
    body: PartnerProvisionBody,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Idempotent DEML account → FORJD tenant + ``fjsvc_`` mint.

    End users never call this. DEML's control plane uses ``FORJD_PROVISION_TOKEN``.
    """
    _require_provision_token(authorization)
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        return await provision_svc.provision_partner_tenant(
            pool,
            external_ref=body.external_ref,
            partner=body.partner,
            slug=body.slug,
            name=body.name,
            include_tenant_erase=body.include_tenant_erase,
            remint_if_exists=body.remint_if_exists,
        )
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_400_BAD_REQUEST
        if "slug already taken" in detail or "conflict" in detail:
            code = status.HTTP_409_CONFLICT
        raise HTTPException(code, detail=detail) from exc
