"""Crypto session directory — public X25519 keys only (server-blind)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.core.config import settings
from app.models.session import CryptoSessionUpsert
from app.services import tenants as tenant_svc


# --- Bind envelope.key_id → active crypto_sessions.session_id ---
async def require_active_session(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    key_id: str,
) -> None:
    """Fail closed when ingest key_id is not a registered, non-expired session.

    Controlled by REQUIRE_CRYPTO_SESSION (forced true in production).
    """
    if not settings.REQUIRE_CRYPTO_SESSION:
        return
    row = await pool.fetchrow(
        """
        SELECT 1
        FROM crypto_sessions
        WHERE tenant_id = $1::uuid
          AND session_id = $2
          AND (expires_at IS NULL OR expires_at > NOW())
        """,
        str(tenant_id),
        key_id,
    )
    if row is None:
        raise ValueError(
            "envelope.key_id must match an active crypto_sessions.session_id"
        )


# --- Upsert public keys for a device session ---
async def upsert_session(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    body: CryptoSessionUpsert,
) -> dict[str, Any]:
    await tenant_svc.ensure_secure_schema(pool)
    await tenant_svc.require_member(
        pool,
        tenant_id=body.tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin", "member"}),
    )

    # Only the owning user may update an existing session_id (WHERE clause).
    row = await pool.fetchrow(
        """
        INSERT INTO crypto_sessions (
            tenant_id, session_id, user_id,
            identity_public_key, ephemeral_public_key, ratchet_state_hint, expires_at
        )
        VALUES ($1::uuid, $2, $3::uuid, $4, $5, $6, $7)
        ON CONFLICT (tenant_id, session_id) DO UPDATE SET
            identity_public_key = EXCLUDED.identity_public_key,
            ephemeral_public_key = EXCLUDED.ephemeral_public_key,
            ratchet_state_hint = EXCLUDED.ratchet_state_hint,
            expires_at = EXCLUDED.expires_at,
            updated_at = NOW()
        WHERE crypto_sessions.user_id = EXCLUDED.user_id
        RETURNING id::text, tenant_id::text, session_id, user_id::text,
                  identity_public_key, ephemeral_public_key, ratchet_state_hint,
                  created_at, updated_at, expires_at
        """,
        str(body.tenant_id),
        body.session_id,
        user.user_id,
        body.identity_public_key,
        body.ephemeral_public_key,
        body.ratchet_state_hint,
        body.expires_at,
    )
    if row is None:
        # Conflict owned by another user.
        raise PermissionError("session_id owned by another user")
    return _row_out(row)


# --- List non-expired sessions for peer discovery ---
async def list_sessions(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    limit: int = 50,
) -> list[dict[str, Any]]:
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, session_id, user_id::text,
               identity_public_key, ephemeral_public_key, ratchet_state_hint,
               created_at, updated_at, expires_at
        FROM crypto_sessions
        WHERE tenant_id = $1::uuid
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY updated_at DESC
        LIMIT $2
        """,
        str(tenant_id),
        limit,
    )
    return [_row_out(r) for r in rows]


# --- Serialize DB row for API responses ---
def _row_out(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "session_id": row["session_id"],
        "user_id": row["user_id"],
        "identity_public_key": row["identity_public_key"],
        "ephemeral_public_key": row["ephemeral_public_key"],
        "ratchet_state_hint": row["ratchet_state_hint"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
    }
