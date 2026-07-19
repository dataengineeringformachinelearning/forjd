"""SOC incident cases — tenant-scoped, opaque actor_id (no Django User join)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status

from app.core.auth import AuthUser
from app.core.config import settings
from app.services import audit
from app.services import tenants as tenant_svc
from app.services.correlation import CorrelationMatch, evaluate_correlation_rules


# --- Soft schema ---
async def ensure_soc_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    if not settings.SOFT_MIGRATE_SCHEMA:
        secure = await pool.fetchval(
            """
            SELECT COUNT(*) = 2
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
              JOIN information_schema.columns col
                ON col.table_schema = n.nspname AND col.table_name = c.relname
              WHERE n.nspname = 'public' AND c.relname = 'incident_cases'
                AND c.relrowsecurity = TRUE
                AND col.column_name IN ('source_signal_id', 'source_correlation_id')
            """
        )
        if not secure:
            raise RuntimeError("secure case schema missing; apply backend/sql/020")
        return
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
            source_signal_id UUID,
            source_correlation_id UUID,
            correlation_rule_ids TEXT[] NOT NULL DEFAULT '{}',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by_actor_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute("ALTER TABLE incident_cases ADD COLUMN IF NOT EXISTS source_signal_id UUID")
    await pool.execute(
        "ALTER TABLE incident_cases ADD COLUMN IF NOT EXISTS source_correlation_id UUID"
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS incident_cases_source_signal_uidx
        ON incident_cases (tenant_id, source_signal_id)
        WHERE source_signal_id IS NOT NULL
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS incident_cases_source_correlation_uidx
        ON incident_cases (tenant_id, source_correlation_id)
        WHERE source_correlation_id IS NOT NULL
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
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"cases:write"}),
    )
    await ensure_soc_schema(pool)
    await audit.record_required(
        pool,
        action="case.create_attempt",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="incident_case",
        details={"severity": severity, "source": "manual"},
    )
    row = await pool.fetchrow(
        """
        INSERT INTO incident_cases (
            tenant_id, title, description, severity, metadata, created_by_actor_id
        )
        VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6::uuid)
        RETURNING id::text, tenant_id::text, title, description, status, severity,
                  assigned_actor_id::text, source_signal_id::text,
                  source_correlation_id::text,
                  correlation_rule_ids, metadata,
                  created_by_actor_id::text, created_at, updated_at
        """,
        str(tenant_id),
        title.strip(),
        description,
        severity,
        json.dumps(metadata or {}),
        user.user_id,
    )
    out = _case_dict(row)
    await audit.record_required(
        pool,
        action="case.create",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="incident_case",
        resource_id=out["id"],
        details={"severity": severity, "source": "manual"},
    )
    return out


async def list_cases(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    limit: int = 100,
) -> list[dict[str, Any]]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"cases:read"}),
    )
    await ensure_soc_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, title, description, status, severity,
               assigned_actor_id::text, source_signal_id::text,
               source_correlation_id::text,
               correlation_rule_ids, metadata,
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


async def update_case(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    case_id: UUID,
    updates: dict[str, Any],
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"cases:write"}),
    )
    await ensure_soc_schema(pool)
    allowed = {
        "title": "text",
        "description": "text",
        "status": "text",
        "severity": "text",
        "assigned_actor_id": "uuid",
        "metadata": "jsonb",
    }
    clean = {key: value for key, value in updates.items() if key in allowed}
    if not clean:
        raise ValueError("at least one case field must be supplied")
    assigned_actor_id = clean.get("assigned_actor_id")
    if assigned_actor_id is not None:
        owns_actor = await pool.fetchval(
            """
            SELECT EXISTS (
              SELECT 1 FROM tenant_members
              WHERE tenant_id = $1::uuid AND user_id = $2::uuid
              UNION ALL
              SELECT 1 FROM service_accounts
              WHERE tenant_id = $1::uuid AND id = $2::uuid
                AND is_active = TRUE AND revoked_at IS NULL
            )
            """,
            str(tenant_id),
            str(assigned_actor_id),
        )
        if not owns_actor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assignee not found")
    await audit.record_required(
        pool,
        action="case.update_attempt",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="incident_case",
        resource_id=str(case_id),
        details={"fields": sorted(clean)},
    )
    args: list[Any] = [str(case_id), str(tenant_id)]
    assignments: list[str] = []
    for key, value in clean.items():
        args.append(json.dumps(value) if key == "metadata" else value)
        assignments.append(f"{key} = ${len(args)}::{allowed[key]}")
    row = await pool.fetchrow(
        f"""
        UPDATE incident_cases
        SET {", ".join(assignments)}, updated_at = NOW()
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        RETURNING id::text, tenant_id::text, title, description, status, severity,
                  assigned_actor_id::text, source_signal_id::text,
                  source_correlation_id::text,
                  correlation_rule_ids, metadata,
                  created_by_actor_id::text, created_at, updated_at
        """,
        *args,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")
    out = _case_dict(row)
    await audit.record_required(
        pool,
        action="case.update",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="incident_case",
        resource_id=str(case_id),
        details={"fields": sorted(clean)},
    )
    return out


# --- Correlate context → open case ---
async def open_case_from_context(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    context: dict[str, Any],
    source_signal_id: UUID | None = None,
    source_correlation_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Evaluate correlation rules and idempotently open a tenant-scoped case."""
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"cases:write"}),
    )
    matches = evaluate_correlation_rules(context)
    if not matches:
        return None
    await ensure_soc_schema(pool)
    primary = matches[0]
    await audit.record_required(
        pool,
        action="case.correlate_attempt",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="incident_case",
        resource_id=(
            str(source_signal_id or source_correlation_id)
            if source_signal_id or source_correlation_id
            else "unkeyed"
        ),
        details={"rule_ids": [m.rule_id for m in matches]},
    )
    args = (
        str(tenant_id),
        primary.title,
        primary.description,
        primary.severity,
        [m.rule_id for m in matches],
        json.dumps({"context": context, "matches": [_match_dict(m) for m in matches]}),
        user.user_id,
        str(source_signal_id) if source_signal_id else None,
        str(source_correlation_id) if source_correlation_id else None,
    )
    row = await pool.fetchrow(
        """
        INSERT INTO incident_cases (
            tenant_id, title, description, severity, correlation_rule_ids,
            metadata, created_by_actor_id, source_signal_id, source_correlation_id
        )
        VALUES (
            $1::uuid, $2, $3, $4, $5::text[], $6::jsonb,
            $7::uuid, $8::uuid, $9::uuid
        )
        ON CONFLICT DO NOTHING
        RETURNING id::text, tenant_id::text, title, description, status, severity,
                  assigned_actor_id::text, source_signal_id::text,
                  source_correlation_id::text,
                  correlation_rule_ids, metadata,
                  created_by_actor_id::text, created_at, updated_at
        """,
        *args,
    )
    created = row is not None
    if row is None and (source_signal_id is not None or source_correlation_id is not None):
        row = await pool.fetchrow(
            """
            SELECT id::text, tenant_id::text, title, description, status, severity,
                   assigned_actor_id::text, source_signal_id::text,
                   source_correlation_id::text,
                   correlation_rule_ids, metadata,
                   created_by_actor_id::text, created_at, updated_at
            FROM incident_cases
            WHERE tenant_id = $1::uuid
              AND (
                ($2::uuid IS NOT NULL AND source_signal_id = $2::uuid)
                OR ($3::uuid IS NOT NULL AND source_correlation_id = $3::uuid)
              )
            """,
            str(tenant_id),
            str(source_signal_id) if source_signal_id else None,
            str(source_correlation_id) if source_correlation_id else None,
        )
    if row is None:
        return None
    out = _case_dict(row)
    if created:
        await audit.record_required(
            pool,
            action="case.correlated",
            actor_user_id=user.actor_id,
            tenant_id=tenant_id,
            resource_type="incident_case",
            resource_id=out["id"],
            details={
                "rule_ids": [m.rule_id for m in matches],
                "source_signal_id": str(source_signal_id) if source_signal_id else None,
                "source_correlation_id": (
                    str(source_correlation_id) if source_correlation_id else None
                ),
            },
        )
    return out


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
        "source_signal_id": row["source_signal_id"],
        "source_correlation_id": row["source_correlation_id"],
        "correlation_rule_ids": list(row["correlation_rule_ids"] or []),
        "metadata": row["metadata"] if isinstance(row["metadata"], dict) else {},
        "created_by_actor_id": row["created_by_actor_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
