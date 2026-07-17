"""Tenant membership helpers (service-role DB access after JWT verification)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger("forjd.tenants")

# Tables that must exist with RLS when REQUIRE_RLS is set.
_RLS_TABLES = (
    "tenants",
    "tenant_members",
    "telemetry_events",
    "crypto_sessions",
    "stream_results",
    "projection_checkpoints",
    "projection_dlq",
    "status_pages",
)


# --- Schema readiness (fail closed in production) ---
async def assert_secure_schema(pool: asyncpg.Pool) -> None:
    """Ensure required tables exist; optionally require RLS enabled."""
    missing: list[str] = []
    for table in _RLS_TABLES:
        exists = await pool.fetchval(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema = 'public' AND table_name = $1
            )
            """,
            table,
        )
        if not exists:
            missing.append(table)
    if missing:
        raise RuntimeError(
            "secure schema incomplete — apply backend/sql/003–008; missing: "
            + ", ".join(missing)
        )

    if not settings.REQUIRE_RLS:
        return

    no_rls: list[str] = []
    for table in _RLS_TABLES:
        enabled = await pool.fetchval(
            """
            SELECT relrowsecurity FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = $1
            """,
            table,
        )
        if not enabled:
            no_rls.append(table)
    if no_rls:
        raise RuntimeError(
            "RLS required but disabled on: " + ", ".join(no_rls)
        )


# --- Local soft-migrate (shapes only; full RLS needs sql/003–008) ---
async def ensure_secure_schema(pool: asyncpg.Pool) -> None:
    """Ensure schema for local/dev; production asserts migrations + RLS.

    Soft-migrate creates table shapes without policies — never used when
    ENVIRONMENT=production (SOFT_MIGRATE_SCHEMA forced false).
    """
    if not settings.SOFT_MIGRATE_SCHEMA:
        await assert_secure_schema(pool)
        return

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
            content_type TEXT NOT NULL DEFAULT 'application/forjd-event+v1',
            event_type TEXT,
            schema_version INT NOT NULL DEFAULT 1,
            workflow_id TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            UNIQUE (tenant_id, client_event_id)
        )
        """
    )
    # Additive columns when an older soft-migrate shape already exists.
    await pool.execute(
        "ALTER TABLE telemetry_events ADD COLUMN IF NOT EXISTS event_type TEXT"
    )
    await pool.execute(
        "ALTER TABLE telemetry_events ADD COLUMN IF NOT EXISTS workflow_id TEXT"
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
    # Pathway/Prefect outputs (metadata scores only — see sql/005).
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS stream_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            telemetry_event_id UUID REFERENCES telemetry_events (id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            kind TEXT NOT NULL DEFAULT 'rollup',
            engine TEXT NOT NULL DEFAULT 'pathway',
            score DOUBLE PRECISION,
            is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
            features JSONB NOT NULL DEFAULT '{}'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            workflow_id TEXT
        )
        """
    )
    await pool.execute(
        "ALTER TABLE stream_results ADD COLUMN IF NOT EXISTS workflow_id TEXT"
    )
    await pool.execute(
        "ALTER TABLE stream_results ADD COLUMN IF NOT EXISTS projection_name TEXT"
    )
    await pool.execute(
        "ALTER TABLE stream_results ADD COLUMN IF NOT EXISTS source_event_id UUID"
    )
    await pool.execute(
        """
        ALTER TABLE stream_results
        ADD COLUMN IF NOT EXISTS projection_version INT NOT NULL DEFAULT 1
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS use_cases (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            content_types TEXT[] NOT NULL DEFAULT '{}',
            event_types TEXT[] NOT NULL DEFAULT '{}',
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
    # Durable projections + DLQ + status pages (shapes; RLS via sql/007–008).
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS projection_checkpoints (
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            projection_name TEXT NOT NULL,
            workflow_id TEXT NOT NULL DEFAULT '',
            last_event_id UUID,
            last_created_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (tenant_id, projection_name, workflow_id)
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS projection_dlq (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            source_event_id UUID,
            workflow_id TEXT,
            projection_name TEXT NOT NULL,
            error TEXT NOT NULL,
            payload_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
            attempts INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS status_pages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_published BOOLEAN NOT NULL DEFAULT FALSE,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS status_services (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            page_id UUID NOT NULL REFERENCES status_pages (id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'operational',
            description TEXT NOT NULL DEFAULT '',
            sort_order INT NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS status_incidents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            page_id UUID NOT NULL REFERENCES status_pages (id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'investigating',
            severity TEXT NOT NULL DEFAULT 'minor',
            body TEXT NOT NULL DEFAULT '',
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
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
