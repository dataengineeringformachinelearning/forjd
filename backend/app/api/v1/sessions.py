"""X25519 crypto session directory API (public keys only).

Gated by human membership or tenant-scoped service token (`sessions:*`).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.session import CryptoSessionUpsert
from app.services import sessions as session_svc

router = APIRouter(prefix="/sessions", tags=["sessions"])


# --- Publish / rotate public keys ---
@router.post("")
async def upsert_session(
    request: Request,
    body: CryptoSessionUpsert,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Publish or rotate a device session's X25519 *public* keys.

    Private keys must never be sent. Peers use these pubs for ECDH locally;
    FORJD never derives message keys from this registry on the E2EE path.
    """
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        session = await session_svc.upsert_session(pool, user=user, body=body)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "session": session}


# --- Peer discovery (public material only) ---
@router.get("")
async def list_sessions(
    request: Request,
    tenant_id: UUID,
    limit: int = 50,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List non-expired public sessions for a tenant (peer discovery)."""
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    limit = max(1, min(limit, 100))
    sessions = await session_svc.list_sessions(pool, user=user, tenant_id=tenant_id, limit=limit)
    return {"ok": True, "tenant_id": str(tenant_id), "sessions": sessions}


# --- Revoke compromised / logged-out device session ---
@router.delete("/{session_id}")
async def revoke_session(
    request: Request,
    session_id: str,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Revoke a session so its key_id can no longer ingest sealed events."""
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        session = await session_svc.revoke_session(
            pool, user=user, tenant_id=tenant_id, session_id=session_id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True, "session": session}
