"""Honeypot endpoints + interaction analysis ."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.services import tenants as tenant_svc

TRAP_TYPES = (
    "env_file",
    "admin_panel",
    "wordpress_login",
    "gitlab",
    "docker_compose",
    "database_config",
    "api_secret",
    "generic",
)


async def ensure_honeypot_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS honeypot_endpoints (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            trap_type TEXT NOT NULL DEFAULT 'generic',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, path)
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS honeypot_interactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            honeypot_id UUID NOT NULL REFERENCES honeypot_endpoints (id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            source_ip INET,
            method TEXT NOT NULL DEFAULT 'GET',
            user_agent TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


async def create_honeypot(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    path: str,
    trap_type: str = "generic",
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool, tenant_id=tenant_id, user_id=user.user_id, min_roles=frozenset({"owner", "admin"})
    )
    if trap_type not in TRAP_TYPES:
        raise ValueError(f"invalid trap_type; allowed={TRAP_TYPES}")
    await ensure_honeypot_schema(pool)
    row = await pool.fetchrow(
        """
        INSERT INTO honeypot_endpoints (tenant_id, path, trap_type)
        VALUES ($1::uuid, $2, $3)
        ON CONFLICT (tenant_id, path) DO UPDATE SET trap_type = EXCLUDED.trap_type, is_active = TRUE
        RETURNING id::text, tenant_id::text, path, trap_type, is_active, created_at
        """,
        str(tenant_id),
        path if path.startswith("/") else f"/{path}",
        trap_type,
    )
    return dict(row)


async def log_interaction(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    path: str,
    source_ip: str | None,
    method: str = "GET",
    user_agent: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    await ensure_honeypot_schema(pool)
    hp = await pool.fetchrow(
        """
        SELECT id::text FROM honeypot_endpoints
        WHERE tenant_id = $1::uuid AND path = $2 AND is_active = TRUE
        """,
        str(tenant_id),
        path,
    )
    if hp is None:
        return None
    row = await pool.fetchrow(
        """
        INSERT INTO honeypot_interactions (
            honeypot_id, tenant_id, source_ip, method, user_agent, payload
        )
        VALUES ($1::uuid, $2::uuid, $3::inet, $4, $5, $6::jsonb)
        RETURNING id::text, honeypot_id::text, host(source_ip) AS source_ip, method, created_at
        """,
        hp["id"],
        str(tenant_id),
        source_ip,
        method.upper(),
        user_agent,
        json.dumps(payload or {}),
    )
    return dict(row)


async def analyze_honeypot_threats(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
) -> dict[str, Any]:
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    await ensure_honeypot_schema(pool)
    total = await pool.fetchval(
        """
        SELECT COUNT(*)::int FROM honeypot_interactions
        WHERE tenant_id = $1::uuid AND created_at >= NOW() - INTERVAL '90 days'
        """,
        str(tenant_id),
    )
    unique_ips = await pool.fetchval(
        """
        SELECT COUNT(DISTINCT source_ip)::int FROM honeypot_interactions
        WHERE tenant_id = $1::uuid AND created_at >= NOW() - INTERVAL '90 days'
        """,
        str(tenant_id),
    )
    suspicious = await pool.fetchval(
        """
        SELECT COUNT(*)::int FROM (
          SELECT source_ip FROM honeypot_interactions
          WHERE tenant_id = $1::uuid AND created_at >= NOW() - INTERVAL '90 days'
          GROUP BY source_ip HAVING COUNT(*) > 5
        ) s
        """,
        str(tenant_id),
    )
    by_trap = await pool.fetch(
        """
        SELECT h.trap_type, COUNT(i.id)::int AS hits
        FROM honeypot_endpoints h
        LEFT JOIN honeypot_interactions i ON i.honeypot_id = h.id
          AND i.created_at >= NOW() - INTERVAL '90 days'
        WHERE h.tenant_id = $1::uuid
        GROUP BY h.trap_type
        """,
        str(tenant_id),
    )
    post_hits = await pool.fetchval(
        """
        SELECT COUNT(*)::int FROM honeypot_interactions
        WHERE tenant_id = $1::uuid AND method = 'POST'
          AND created_at >= NOW() - INTERVAL '90 days'
        """,
        str(tenant_id),
    )
    total_f = float(total or 0)
    unique_f = float(unique_ips or 0)
    features = [
        min(1.0, total_f / 100.0),
        (float(post_hits or 0) / total_f) if total_f else 0.0,
        (unique_f / total_f) if total_f else 0.0,
        0.5,
        0.5,
        0.5,
    ]
    honeypot_score = (
        min(100.0, (total_f / max(1.0, unique_f * 10.0)) * 100.0) if unique_f > 0 else 0.0
    )
    return {
        "ok": True,
        "total_interactions": int(total or 0),
        "unique_ips": int(unique_ips or 0),
        "suspicious_ips": int(suspicious or 0),
        "trap_effectiveness": {r["trap_type"]: r["hits"] for r in by_trap},
        "honeypot_score": honeypot_score,
        "threat_vectors": features,
    }
