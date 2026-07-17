"""SOC incident cases — tenant-scoped, opaque actor_id (no Django User join)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.services import tenants as tenant_svc
from app.services.correlation import CorrelationMatch, evaluate_correlation_rules


# --- Soft schema ---
async def ensure_soc_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS incident_cases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            severity TEXT NOT NULL DEFAULT 'medium',
            assigned_actor_id UUID,
            status_incident_id UUID,
            correlation_rule_ids TEXT[] NOT NULL DEFAULT '{}',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by_actor_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


# --- CRUD ---
async def create_case(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    title: str,
    description: str = "",
    severity: str = "medium",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin", "member"}),
    )
    await ensure_soc_schema(pool)
    row = await pool.fetchrow(
        """
        INSERT INTO incident_cases (
            tenant_id, title, description, severity, metadata, created_by_actor_id
        )
        VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6::uuid)
        RETURNING id::text, tenant_id::text, title, description, status, severity,
                  assigned_actor_id::text, correlation_rule_ids, metadata,
                  created_by_actor_id::text, created_at, updated_at
        """,
        str(tenant_id),
        title.strip(),
        description,
        severity,
        json.dumps(metadata or {}),
        user.user_id,
    )
    return _case_dict(row)


async def list_cases(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    limit: int = 100,
) -> list[dict[str, Any]]:
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    await ensure_soc_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, title, description, status, severity,
               assigned_actor_id::text, correlation_rule_ids, metadata,
               created_by_actor_id::text, created_at, updated_at
        FROM incident_cases
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        str(tenant_id),
        max(1, min(limit, 500)),
    )
    return [_case_dict(r) for r in rows]


# --- Correlate context → open case ---
async def open_case_from_context(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    context: dict[str, Any],
    actor_id: str | None = None,
) -> dict[str, Any] | None:
    """Evaluate correlation rules; open a case when any match (service-role path)."""
    matches = evaluate_correlation_rules(context)
    if not matches:
        return None
    await ensure_soc_schema(pool)
    primary = matches[0]
    row = await pool.fetchrow(
        """
        INSERT INTO incident_cases (
            tenant_id, title, description, severity, correlation_rule_ids,
            metadata, created_by_actor_id
        )
        VALUES ($1::uuid, $2, $3, $4, $5::text[], $6::jsonb, $7::uuid)
        RETURNING id::text, tenant_id::text, title, description, status, severity,
                  assigned_actor_id::text, correlation_rule_ids, metadata,
                  created_by_actor_id::text, created_at, updated_at
        """,
        str(tenant_id),
        primary.title,
        primary.description,
        primary.severity,
        [m.rule_id for m in matches],
        json.dumps({"context": context, "matches": [_match_dict(m) for m in matches]}),
        actor_id,
    )
    return _case_dict(row)


def _match_dict(m: CorrelationMatch) -> dict[str, str]:
    return {
        "rule_id": m.rule_id,
        "title": m.title,
        "severity": m.severity,
        "description": m.description,
    }


def _case_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "severity": row["severity"],
        "assigned_actor_id": row["assigned_actor_id"],
        "correlation_rule_ids": list(row["correlation_rule_ids"] or []),
        "metadata": row["metadata"] if isinstance(row["metadata"], dict) else {},
        "created_by_actor_id": row["created_by_actor_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
