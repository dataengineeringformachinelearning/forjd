"""Tenant membership helpers (service-role DB access after JWT verification)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status

logger = logging.getLogger("forjd.tenants")


# --- Local soft-migrate (shapes only; full RLS needs sql/003 + sql/004) ---
async def ensure_secure_schema(pool: asyncpg.Pool) -> None:
    """Soft-create core tables if SQL migration was not applied yet.

    Full RLS policies still require running `sql/003_secure_tenancy.sql` in Supabase
    (needs `auth.users` FKs + policy grants). This only creates the shapes for local.
    """
    try:
        await pool.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    except asyncpg.PostgresError as exc:
        logger.warning("pgcrypto extension: %s", exc)
    try:
        await pool.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    except asyncpg.PostgresError as exc:
        logger.warning("vector extension: %s", exc)

    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            key_directory_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_members (
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            user_id UUID NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (tenant_id, user_id)
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS telemetry_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            submitted_by UUID,
            client_event_id TEXT NOT NULL,
            occurred_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            algo TEXT NOT NULL DEFAULT 'aes-256-gcm',
            key_id TEXT NOT NULL,
            ratchet_header TEXT,
            nonce TEXT NOT NULL,
            ciphertext TEXT NOT NULL,
            ciphertext_sha256 TEXT,
            content_type TEXT NOT NULL DEFAULT 'application/forjd-telemetry+v1',
            schema_version INT NOT NULL DEFAULT 1,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            UNIQUE (tenant_id, client_event_id)
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_vectors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            telemetry_event_id UUID REFERENCES telemetry_events (id) ON DELETE SET NULL,
            series_id TEXT NOT NULL DEFAULT 'default',
            model_version TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            embedding vector(16),
            reconstruction_error DOUBLE PRECISION,
            is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
            context_ciphertext TEXT,
            context_nonce TEXT,
            context_key_id TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    # Public X25519 keys only — private keys never stored (see sql/004).
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS crypto_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            user_id UUID NOT NULL,
            identity_public_key TEXT NOT NULL,
            ephemeral_public_key TEXT,
            ratchet_state_hint TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ,
            UNIQUE (tenant_id, session_id)
        )
        """
    )


# --- Membership checks ---
async def user_role_in_tenant(
    pool: asyncpg.Pool, *, tenant_id: UUID, user_id: str
) -> str | None:
    row = await pool.fetchrow(
        """
        SELECT role FROM tenant_members
        WHERE tenant_id = $1::uuid AND user_id = $2::uuid
        """,
        str(tenant_id),
        user_id,
    )
    return str(row["role"]) if row else None


async def require_member(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    user_id: str,
    min_roles: frozenset[str] | None = None,
) -> str:
    role = await user_role_in_tenant(pool, tenant_id=tenant_id, user_id=user_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a tenant member")
    if min_roles is not None and role not in min_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
    return role


# --- Tenant CRUD ---
async def create_tenant(
    pool: asyncpg.Pool,
    *,
    slug: str,
    name: str,
    owner_user_id: str,
    key_directory_id: str | None = None,
) -> dict[str, Any]:
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO tenants (slug, name, key_directory_id)
            VALUES ($1, $2, $3)
            RETURNING id::text, slug, name, key_directory_id, created_at
            """,
            slug,
            name,
            key_directory_id,
        )
        await conn.execute(
            """
            INSERT INTO tenant_members (tenant_id, user_id, role)
            VALUES ($1::uuid, $2::uuid, 'owner')
            """,
            row["id"],
            owner_user_id,
        )
    return {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "key_directory_id": row["key_directory_id"],
        "created_at": row["created_at"],
        "role": "owner",
    }


async def list_tenants_for_user(pool: asyncpg.Pool, *, user_id: str) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT t.id::text, t.slug, t.name, t.key_directory_id, t.created_at, m.role
        FROM tenants t
        JOIN tenant_members m ON m.tenant_id = t.id
        WHERE m.user_id = $1::uuid
        ORDER BY t.created_at DESC
        """,
        user_id,
    )
    return [
        {
            "id": r["id"],
            "slug": r["slug"],
            "name": r["name"],
            "key_directory_id": r["key_directory_id"],
            "created_at": r["created_at"],
            "role": r["role"],
        }
        for r in rows
    ]
