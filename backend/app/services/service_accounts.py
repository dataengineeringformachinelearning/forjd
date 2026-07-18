"""Tenant-scoped service accounts for M2M / subprocessors.

Issuance is human-only (owner/admin). Tokens are shown once at create time.
Auth verification lives in `app.core.auth`; this module owns persistence.
"""

from __future__ import annotations

import hmac
import logging
import secrets
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status

from app.core.auth import (
    SERVICE_PREFIX_LEN,
    SERVICE_TOKEN_PREFIX,
    AuthUser,
    hash_service_token,
    require_user_principal,
)
from app.services import audit
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.service_accounts")

# --- Default scopes for SaaS subprocessors ---
# sessions:* — register X25519 pubs when REQUIRE_CRYPTO_SESSION=true
# replay:* / status:* / analytics:read — partner control-plane adapters
# (human mint still required for the token itself).
DEFAULT_SCOPES: tuple[str, ...] = (
    "ingest:write",
    "ingest:read",
    "projections:read",
    "projections:run",
    "sessions:write",
    "sessions:read",
    "replay:read",
    "replay:write",
    "status:read",
    "status:write",
    "analytics:read",
    # Partner product-domain adapters (sql/018) — remint existing tokens.
    "exports:read",
    "exports:write",
    "vulnerabilities:read",
    "vulnerabilities:write",
    "integrations:write",
    "tenants:erase",
)

ALLOWED_SCOPES = frozenset(
    {
        *DEFAULT_SCOPES,
        "analytics:write",
        "*",
    }
)


# --- Soft-migrate table shape (production applies sql/014) ---
async def ensure_schema(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS service_accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            subprocessor TEXT NOT NULL DEFAULT '',
            prefix TEXT UNIQUE,
            key_hash TEXT,
            auth_user_id UUID UNIQUE,
            scopes TEXT[] NOT NULL DEFAULT ARRAY[
                'ingest:write', 'ingest:read',
                'projections:read', 'projections:run',
                'sessions:write', 'sessions:read',
                'replay:read', 'replay:write',
                'status:read', 'status:write',
                'analytics:read'
            ]::text[],
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            revoked_at TIMESTAMPTZ,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMPTZ
        )
        """
    )


def _normalize_scopes(scopes: list[str] | None) -> list[str]:
    if not scopes:
        return list(DEFAULT_SCOPES)
    out: list[str] = []
    for s in scopes:
        key = str(s).strip()
        if key not in ALLOWED_SCOPES:
            raise ValueError(f"unknown scope: {key!r}")
        if key not in out:
            out.append(key)
    return out


def _mint_opaque_token() -> tuple[str, str, str]:
    """Return (full_token, prefix, key_hash). Full token shown once to the caller."""
    prefix = secrets.token_hex(SERVICE_PREFIX_LEN // 2)  # 8 hex chars
    secret = secrets.token_urlsafe(32)
    token = f"{SERVICE_TOKEN_PREFIX}{prefix}_{secret}"
    return token, prefix, hash_service_token(token)


def _public_row(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "tenant_id": str(row["tenant_id"]),
        "name": row["name"],
        "subprocessor": row["subprocessor"] or "",
        "prefix": row["prefix"],
        "auth_user_id": str(row["auth_user_id"]) if row["auth_user_id"] else None,
        "scopes": list(row["scopes"] or []),
        "is_active": bool(row["is_active"]) and row["revoked_at"] is None,
        "revoked_at": row["revoked_at"],
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_used_at": row["last_used_at"],
    }


# --- Auth lookups (used by app.core.auth) ---
async def authenticate_opaque(
    pool: asyncpg.Pool, *, prefix: str, token: str
) -> dict[str, Any] | None:
    await ensure_schema(pool)
    row = await pool.fetchrow(
        """
        SELECT id, tenant_id, name, subprocessor, scopes, key_hash,
               is_active, revoked_at
        FROM service_accounts
        WHERE prefix = $1
        """,
        prefix,
    )
    if row is None or not row["is_active"] or row["revoked_at"] is not None:
        return None
    expected = row["key_hash"]
    if not expected or not hmac.compare_digest(hash_service_token(token), expected):
        return None
    await pool.execute(
        "UPDATE service_accounts SET last_used_at = NOW() WHERE id = $1::uuid",
        str(row["id"]),
    )
    return dict(row)


async def authenticate_auth_user(pool: asyncpg.Pool, *, auth_user_id: str) -> dict[str, Any] | None:
    await ensure_schema(pool)
    row = await pool.fetchrow(
        """
        SELECT id, tenant_id, name, subprocessor, scopes,
               is_active, revoked_at
        FROM service_accounts
        WHERE auth_user_id = $1::uuid
        """,
        auth_user_id,
    )
    if row is None or not row["is_active"] or row["revoked_at"] is not None:
        return None
    await pool.execute(
        "UPDATE service_accounts SET last_used_at = NOW() WHERE id = $1::uuid",
        str(row["id"]),
    )
    return dict(row)


# --- Management (enterprise user JWT only) ---
async def create_service_account(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    name: str,
    subprocessor: str = "",
    scopes: list[str] | None = None,
    auth_user_id: UUID | None = None,
    mint_opaque_token: bool = True,
) -> dict[str, Any]:
    require_user_principal(user)
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin"}),
    )
    await ensure_schema(pool)
    clean_scopes = _normalize_scopes(scopes)
    if not mint_opaque_token and auth_user_id is None:
        raise ValueError("auth_user_id required when mint_opaque_token is false")

    token: str | None = None
    prefix: str | None = None
    key_hash: str | None = None
    if mint_opaque_token:
        token, prefix, key_hash = _mint_opaque_token()

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO service_accounts (
                tenant_id, name, subprocessor, prefix, key_hash,
                auth_user_id, scopes, created_by
            )
            VALUES (
                $1::uuid, $2, $3, $4, $5,
                $6::uuid, $7::text[], $8::uuid
            )
            RETURNING id, tenant_id, name, subprocessor, prefix, auth_user_id,
                      scopes, is_active, revoked_at, created_by,
                      created_at, updated_at, last_used_at
            """,
            str(tenant_id),
            name.strip()[:128],
            (subprocessor or "").strip()[:64],
            prefix,
            key_hash,
            str(auth_user_id) if auth_user_id else None,
            clean_scopes,
            user.user_id,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="service account conflict (prefix or auth_user_id)",
        ) from exc

    assert row is not None
    await audit.record(
        pool,
        action="service_account.create",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="service_account",
        resource_id=str(row["id"]),
        details={
            "subprocessor": row["subprocessor"] or "",
            "scopes": clean_scopes,
            "has_opaque": bool(token),
            "has_auth_user": auth_user_id is not None,
        },
    )
    out = _public_row(row)
    if token:
        # Shown once — never stored in plaintext.
        out["token"] = token
        out["token_hint"] = "Store this token securely; it cannot be retrieved again."
    return out


async def list_service_accounts(
    pool: asyncpg.Pool, *, user: AuthUser, tenant_id: UUID
) -> list[dict[str, Any]]:
    require_user_principal(user)
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin", "member"}),
    )
    await ensure_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id, tenant_id, name, subprocessor, prefix, auth_user_id,
               scopes, is_active, revoked_at, created_by,
               created_at, updated_at, last_used_at
        FROM service_accounts
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        """,
        str(tenant_id),
    )
    return [_public_row(r) for r in rows]


async def revoke_service_account(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    service_account_id: UUID,
) -> dict[str, Any]:
    require_user_principal(user)
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin"}),
    )
    await ensure_schema(pool)
    row = await pool.fetchrow(
        """
        UPDATE service_accounts
        SET is_active = FALSE,
            revoked_at = COALESCE(revoked_at, NOW()),
            updated_at = NOW(),
            key_hash = NULL
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        RETURNING id, tenant_id, name, subprocessor, prefix, auth_user_id,
                  scopes, is_active, revoked_at, created_by,
                  created_at, updated_at, last_used_at
        """,
        str(service_account_id),
        str(tenant_id),
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="service account not found",
        )
    await audit.record(
        pool,
        action="service_account.revoke",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="service_account",
        resource_id=str(service_account_id),
        details={"subprocessor": row["subprocessor"] or ""},
    )
    return _public_row(row)
