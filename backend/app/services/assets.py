"""Tenant assets + vulnerabilities CRUD (tenant_id)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.services import tenants as tenant_svc


async def ensure_asset_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS assets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            hostname TEXT NOT NULL,
            internal_ip INET,
            os_version TEXT,
            mac_address TEXT,
            environment TEXT NOT NULL DEFAULT 'production',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS vulnerabilities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            asset_id UUID REFERENCES assets (id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'triage',
            severity TEXT NOT NULL DEFAULT 'medium',
            impact INT NOT NULL DEFAULT 3,
            likelihood INT NOT NULL DEFAULT 3,
            cve_id TEXT,
            telemetry_context JSONB,
            created_by_actor_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


async def create_asset(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    hostname: str,
    environment: str = "production",
    internal_ip: str | None = None,
    os_version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool, tenant_id=tenant_id, user_id=user.user_id, min_roles=frozenset({"owner", "admin"})
    )
    await ensure_asset_schema(pool)
    row = await pool.fetchrow(
        """
        INSERT INTO assets (
            tenant_id, hostname, environment, internal_ip, os_version, metadata
        )
        VALUES ($1::uuid, $2, $3, $4::inet, $5, $6::jsonb)
        RETURNING id::text, tenant_id::text, hostname, environment,
                  host(internal_ip) AS internal_ip, os_version, created_at
        """,
        str(tenant_id),
        hostname.strip(),
        environment,
        internal_ip,
        os_version,
        json.dumps(metadata or {}),
    )
    return dict(row)


async def list_assets(
    pool: asyncpg.Pool, *, user: AuthUser, tenant_id: UUID, limit: int = 100
) -> list[dict[str, Any]]:
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    await ensure_asset_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, hostname, environment,
               host(internal_ip) AS internal_ip, os_version, created_at
        FROM assets WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC LIMIT $2
        """,
        str(tenant_id),
        max(1, min(limit, 500)),
    )
    return [dict(r) for r in rows]


async def create_vulnerability(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    title: str,
    description: str = "",
    severity: str = "medium",
    status: str = "triage",
    cve_id: str | None = None,
    asset_id: UUID | None = None,
    telemetry_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"vulnerabilities:write"}),
    )
    await ensure_asset_schema(pool)
    row = await pool.fetchrow(
        """
        INSERT INTO vulnerabilities (
            tenant_id, asset_id, title, description, status, severity, cve_id,
            telemetry_context, created_by_actor_id
        )
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8::jsonb, $9::uuid)
        RETURNING id::text, tenant_id::text, asset_id::text, title, description,
                  status, severity, cve_id, created_at
        """,
        str(tenant_id),
        str(asset_id) if asset_id else None,
        title.strip(),
        description,
        status,
        severity,
        cve_id,
        json.dumps(telemetry_context or {}),
        user.user_id,
    )
    return dict(row)


async def list_vulnerabilities(
    pool: asyncpg.Pool, *, user: AuthUser, tenant_id: UUID, limit: int = 100
) -> list[dict[str, Any]]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"vulnerabilities:read"}),
    )
    await ensure_asset_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, asset_id::text, title, description,
               status, severity, cve_id, created_at
        FROM vulnerabilities WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC LIMIT $2
        """,
        str(tenant_id),
        max(1, min(limit, 500)),
    )
    return [dict(r) for r in rows]
