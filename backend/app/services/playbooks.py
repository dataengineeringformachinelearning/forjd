"""Tenant-scoped security playbooks with durable, idempotent run state."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
from fastapi import HTTPException, status

from app.core.auth import AuthUser
from app.core.config import settings
from app.core.worker_health import WorkerHealthRegistry
from app.services import audit
from app.services import tenants as tenant_svc
from app.services.correlation import evaluate_playbook_trigger
from app.services.threat_intel import validate_outbound_url

logger = logging.getLogger("forjd.playbooks")

_CONTROL_PLANE_ACTIONS = frozenset({"email_alert", "block_ip", "revoke_api_key"})
_ACTION_CONFIGURATION_KEYS = {
    "webhook": frozenset({"url", "secret_ref"}),
    "email_alert": frozenset({"template", "channel_ref"}),
    "block_ip": frozenset({"provider_ref", "duration_seconds"}),
    "revoke_api_key": frozenset({"credential_ref"}),
}
_WEBHOOK_MAX_ATTEMPTS = 5
_WEBHOOK_RETRY_BASE_SECONDS = 5
_WEBHOOK_RETRY_CAP_SECONDS = 300
_WEBHOOK_LEASE_SECONDS = 30
_RETRYABLE_WEBHOOK_STATUS_CODES = frozenset({408, 425, 429})


def _webhook_signing_secret(configuration: dict[str, Any]) -> tuple[str, bytes] | None:
    """Resolve one opaque signing reference without persisting or returning its secret."""
    if "secret_ref" not in configuration:
        return None
    secret_ref = configuration.get("secret_ref")
    if not isinstance(secret_ref, str) or not secret_ref:
        raise ValueError("webhook secret_ref is invalid")
    try:
        configured = json.loads(settings.WEBHOOK_SIGNING_SECRETS_JSON or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("webhook signing secret configuration is invalid") from exc
    if not isinstance(configured, dict):
        raise ValueError("webhook signing secret configuration is invalid")
    secret = configured.get(secret_ref)
    if not isinstance(secret, str) or len(secret.encode("utf-8")) < 16:
        raise ValueError("webhook secret_ref is not configured")
    return secret_ref, secret.encode("utf-8")


def _validate_action_configuration(action_type: str, configuration: dict[str, Any]) -> None:
    if action_type == "webhook":
        try:
            _webhook_signing_secret(configuration)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc


async def ensure_playbook_schema(pool: asyncpg.Pool) -> None:
    """Create the development schema shape; production applies sql/020."""
    await tenant_svc.ensure_secure_schema(pool)
    if not settings.SOFT_MIGRATE_SCHEMA:
        secure_count = await pool.fetchval(
            """
            SELECT COUNT(*)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = ANY($1::text[])
              AND c.relrowsecurity = TRUE
            """,
            ["playbooks", "playbook_actions", "playbook_runs", "playbook_action_results"],
        )
        has_required_columns = await pool.fetchval(
            """
            SELECT COUNT(*) = 11
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND (
                (table_name = 'playbooks' AND column_name = 'version')
                OR (table_name = 'playbook_runs' AND column_name = 'playbook_version')
                OR (table_name = 'playbook_runs' AND column_name = 'request_sha256')
                OR (table_name = 'playbook_runs' AND column_name = 'action_plan_snapshot')
                OR (
                  table_name = 'playbook_action_results'
                  AND column_name = 'action_plan_key'
                )
                OR (table_name = 'playbook_action_results' AND column_name = 'max_attempts')
                OR (table_name = 'playbook_action_results' AND column_name = 'next_attempt_at')
                OR (table_name = 'playbook_action_results' AND column_name = 'last_attempt_at')
                OR (table_name = 'playbook_action_results' AND column_name = 'lease_owner')
                OR (table_name = 'playbook_action_results' AND column_name = 'lease_expires_at')
                OR (
                  table_name = 'playbook_action_results'
                  AND column_name = 'configuration_snapshot'
                )
              )
            """
        )
        if int(secure_count or 0) != 4 or not has_required_columns:
            raise RuntimeError("secure SOAR schema missing; apply backend/sql/020")
        return
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS playbooks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            trigger_conditions JSONB NOT NULL DEFAULT '{}'::jsonb,
            version INT NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        "ALTER TABLE playbooks ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1"
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS playbook_actions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            playbook_id UUID NOT NULL REFERENCES playbooks (id) ON DELETE CASCADE,
            action_type TEXT NOT NULL,
            configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
            sort_order INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS playbook_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            playbook_id UUID NOT NULL REFERENCES playbooks (id) ON DELETE CASCADE,
            playbook_version INT NOT NULL CHECK (playbook_version >= 1),
            source_signal_id UUID,
            idempotency_key TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,
            trigger_source TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'running',
            trigger_context JSONB NOT NULL DEFAULT '{}'::jsonb,
            action_plan_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_by_actor_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            CHECK (char_length(idempotency_key) BETWEEN 1 AND 128),
            CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
            CHECK (trigger_source IN ('manual', 'security_signal', 'correlation', 'integration')),
            CHECK (status IN (
                'running', 'retrying', 'awaiting_ack',
                'succeeded', 'partial', 'failed', 'unsupported'
            )),
            CHECK (jsonb_typeof(trigger_context) = 'object'),
            CHECK (
                jsonb_typeof(action_plan_snapshot) = 'array'
                AND jsonb_array_length(action_plan_snapshot) <= 50
            ),
            UNIQUE (tenant_id, idempotency_key)
        )
        """
    )
    await pool.execute("ALTER TABLE playbook_runs ADD COLUMN IF NOT EXISTS request_sha256 TEXT")
    await pool.execute(
        """
        ALTER TABLE playbook_runs
        ADD COLUMN IF NOT EXISTS playbook_version INT NOT NULL DEFAULT 1
        """
    )
    await pool.execute(
        """
        ALTER TABLE playbook_runs
        ADD COLUMN IF NOT EXISTS action_plan_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS playbook_action_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES playbook_runs (id) ON DELETE CASCADE,
            playbook_action_id UUID REFERENCES playbook_actions (id) ON DELETE SET NULL,
            action_plan_key TEXT NOT NULL,
            action_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            attempt INT NOT NULL DEFAULT 1,
            max_attempts INT NOT NULL DEFAULT 5,
            status_code INT,
            error_code TEXT,
            external_reference TEXT,
            configuration_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            result_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            next_attempt_at TIMESTAMPTZ,
            last_attempt_at TIMESTAMPTZ,
            lease_owner TEXT,
            lease_expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            CHECK (status IN (
                'running', 'retry_scheduled', 'awaiting_ack',
                'succeeded', 'failed', 'unsupported'
            )),
            CHECK (attempt BETWEEN 1 AND max_attempts),
            CHECK (max_attempts BETWEEN 1 AND 10),
            CHECK (jsonb_typeof(configuration_snapshot) = 'object'),
            CHECK (jsonb_typeof(result_metadata) = 'object'),
            UNIQUE (run_id, playbook_action_id),
            UNIQUE (run_id, action_plan_key)
        )
        """
    )
    for statement in (
        "ALTER TABLE playbook_action_results ADD COLUMN IF NOT EXISTS max_attempts "
        "INT NOT NULL DEFAULT 5",
        "ALTER TABLE playbook_action_results ADD COLUMN IF NOT EXISTS action_plan_key TEXT",
        "ALTER TABLE playbook_action_results ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ",
        "ALTER TABLE playbook_action_results ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ",
        "ALTER TABLE playbook_action_results ADD COLUMN IF NOT EXISTS lease_owner TEXT",
        "ALTER TABLE playbook_action_results ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ",
        "ALTER TABLE playbook_action_results ADD COLUMN IF NOT EXISTS configuration_snapshot "
        "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ):
        await pool.execute(statement)
    await pool.execute(
        """
        UPDATE playbook_action_results
        SET action_plan_key = COALESCE(playbook_action_id::text, id::text)
        WHERE action_plan_key IS NULL;
        ALTER TABLE playbook_action_results
          ALTER COLUMN action_plan_key SET NOT NULL
        """
    )
    await pool.execute(
        """
        ALTER TABLE playbook_runs
          DROP CONSTRAINT IF EXISTS playbook_runs_status_check;
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'playbook_runs_status_allowed'
              AND conrelid = 'playbook_runs'::regclass
          ) THEN
            ALTER TABLE playbook_runs
              ADD CONSTRAINT playbook_runs_status_allowed CHECK (status IN (
                'running', 'retrying', 'awaiting_ack',
                'succeeded', 'partial', 'failed', 'unsupported'
              ));
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'playbook_runs_action_plan_shape'
              AND conrelid = 'playbook_runs'::regclass
          ) THEN
            ALTER TABLE playbook_runs
              ADD CONSTRAINT playbook_runs_action_plan_shape CHECK (
                jsonb_typeof(action_plan_snapshot) = 'array'
                AND jsonb_array_length(action_plan_snapshot) <= 50
              );
          END IF;
        END $$;

        ALTER TABLE playbook_action_results
          DROP CONSTRAINT IF EXISTS playbook_action_results_status_check;
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'playbook_action_results_retry_contract'
              AND conrelid = 'playbook_action_results'::regclass
          ) THEN
            ALTER TABLE playbook_action_results
              ADD CONSTRAINT playbook_action_results_retry_contract CHECK (
                status IN (
                  'running', 'retry_scheduled', 'awaiting_ack',
                  'succeeded', 'failed', 'unsupported'
                )
                AND max_attempts BETWEEN 1 AND 10
                AND attempt BETWEEN 1 AND max_attempts
                AND (status <> 'retry_scheduled' OR action_type = 'webhook')
                AND ((lease_owner IS NULL) = (lease_expires_at IS NULL))
                AND (status <> 'retry_scheduled' OR next_attempt_at IS NOT NULL)
                AND jsonb_typeof(configuration_snapshot) = 'object'
              );
          END IF;
        END $$
        """
    )
    await pool.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_playbook_run_plan_change()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.action_plan_snapshot IS DISTINCT FROM OLD.action_plan_snapshot THEN
            RAISE EXCEPTION 'playbook run action plan is immutable';
          END IF;
          RETURN NEW;
        END $$;
        DROP TRIGGER IF EXISTS playbook_runs_immutable_plan ON playbook_runs;
        CREATE TRIGGER playbook_runs_immutable_plan
          BEFORE UPDATE OF action_plan_snapshot ON playbook_runs
          FOR EACH ROW EXECUTE FUNCTION prevent_playbook_run_plan_change()
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS playbook_action_results_retry_ready_idx
        ON playbook_action_results (next_attempt_at, created_at, id)
        WHERE action_type = 'webhook' AND status = 'retry_scheduled'
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS playbook_action_results_plan_key_uidx
        ON playbook_action_results (run_id, action_plan_key)
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS playbook_runs_continuation_ready_idx
        ON playbook_runs (updated_at, id)
        WHERE status IN ('running', 'retrying', 'awaiting_ack')
        """
    )


async def _authorize(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    scope: str,
    min_roles: frozenset[str] | None = None,
) -> None:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=min_roles,
        required_scopes=frozenset({scope}),
    )


async def _insert_actions(
    conn: asyncpg.Connection,
    *,
    playbook_id: str,
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, action in enumerate(actions):
        action_type = str(action["action_type"])
        configuration = dict(action.get("configuration") or {})
        _validate_action_configuration(action_type, configuration)
        row = await conn.fetchrow(
            """
            INSERT INTO playbook_actions (playbook_id, action_type, configuration, sort_order)
            VALUES ($1::uuid, $2, $3::jsonb, $4)
            RETURNING id::text, action_type, configuration, sort_order
            """,
            playbook_id,
            action_type,
            json.dumps(configuration),
            int(action.get("sort_order", index)),
        )
        rows.append(_action_dict(row))
    return rows


async def create_playbook(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    name: str,
    description: str = "",
    trigger_conditions: dict[str, Any] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    await _authorize(
        pool,
        user=user,
        tenant_id=tenant_id,
        scope="playbooks:write",
        min_roles=frozenset({"owner", "admin"}),
    )
    await ensure_playbook_schema(pool)
    await audit.record_required(
        pool,
        action="playbook.create_attempt",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="playbook",
        details={"action_count": len(actions or [])},
    )
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO playbooks (tenant_id, name, description, trigger_conditions)
            VALUES ($1::uuid, $2, $3, $4::jsonb)
            RETURNING id::text, tenant_id::text, name, description, is_active,
                      trigger_conditions, version, created_at, updated_at
            """,
            str(tenant_id),
            name.strip(),
            description,
            json.dumps(trigger_conditions or {}),
        )
        action_rows = await _insert_actions(
            conn,
            playbook_id=row["id"],
            actions=actions or [],
        )
    out = _playbook_dict(row)
    out["actions"] = action_rows
    await audit.record_required(
        pool,
        action="playbook.create",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="playbook",
        resource_id=out["id"],
        details={"action_count": len(action_rows)},
    )
    return out


async def update_playbook(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    playbook_id: UUID,
    updates: dict[str, Any],
) -> dict[str, Any]:
    await _authorize(
        pool,
        user=user,
        tenant_id=tenant_id,
        scope="playbooks:write",
        min_roles=frozenset({"owner", "admin"}),
    )
    await ensure_playbook_schema(pool)
    actions = updates.pop("actions", None)
    allowed = {
        "name": "text",
        "description": "text",
        "is_active": "boolean",
        "trigger_conditions": "jsonb",
    }
    clean = {key: value for key, value in updates.items() if key in allowed}
    if not clean and actions is None:
        raise ValueError("at least one playbook field must be supplied")
    await audit.record_required(
        pool,
        action="playbook.update_attempt",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="playbook",
        resource_id=str(playbook_id),
        details={"fields": sorted({*clean, *({"actions"} if actions is not None else set())})},
    )
    async with pool.acquire() as conn, conn.transaction():
        args: list[Any] = [str(playbook_id), str(tenant_id)]
        assignments: list[str] = []
        for key, value in clean.items():
            args.append(json.dumps(value) if key == "trigger_conditions" else value)
            assignments.append(f"{key} = ${len(args)}::{allowed[key]}")
        assignments.extend(["version = version + 1", "updated_at = NOW()"])
        row = await conn.fetchrow(
            f"""
            UPDATE playbooks
            SET {", ".join(assignments)}
            WHERE id = $1::uuid AND tenant_id = $2::uuid
            RETURNING id::text, tenant_id::text, name, description, is_active,
                      trigger_conditions, version, created_at, updated_at
            """,
            *args,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook not found")
        if actions is not None:
            await conn.execute(
                "DELETE FROM playbook_actions WHERE playbook_id = $1::uuid",
                str(playbook_id),
            )
            action_rows = await _insert_actions(
                conn,
                playbook_id=str(playbook_id),
                actions=actions,
            )
        else:
            existing = await conn.fetch(
                """
                SELECT id::text, action_type, configuration, sort_order
                FROM playbook_actions
                WHERE playbook_id = $1::uuid
                ORDER BY sort_order, id
                """,
                str(playbook_id),
            )
            action_rows = [_action_dict(item) for item in existing]
    out = _playbook_dict(row)
    out["actions"] = action_rows
    await audit.record_required(
        pool,
        action="playbook.update",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="playbook",
        resource_id=str(playbook_id),
        details={"fields": sorted({*clean, *({"actions"} if actions is not None else set())})},
    )
    return out


async def list_playbooks(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
) -> list[dict[str, Any]]:
    await _authorize(pool, user=user, tenant_id=tenant_id, scope="playbooks:read")
    await ensure_playbook_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, name, description, is_active,
               trigger_conditions, version, created_at, updated_at
        FROM playbooks
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        """,
        str(tenant_id),
    )
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    action_rows = await pool.fetch(
        """
        SELECT id::text, playbook_id::text, action_type, configuration, sort_order
        FROM playbook_actions
        WHERE playbook_id = ANY($1::uuid[])
        ORDER BY playbook_id, sort_order, id
        """,
        [UUID(item) for item in ids],
    )
    grouped: dict[str, list[dict[str, Any]]] = {item: [] for item in ids}
    for action in action_rows:
        grouped[action["playbook_id"]].append(_action_dict(action))
    out = []
    for row in rows:
        item = _playbook_dict(row)
        item["actions"] = grouped[row["id"]]
        out.append(item)
    return out


async def execute_playbook(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    playbook_id: UUID,
    idempotency_key: str,
    context: dict[str, Any],
    trigger_source: str = "manual",
    source_signal_id: UUID | None = None,
) -> dict[str, Any]:
    """Create one durable run and execute each action at most once per run key."""
    await _authorize(
        pool,
        user=user,
        tenant_id=tenant_id,
        scope="playbooks:execute",
        min_roles=frozenset({"owner", "admin", "member"}),
    )
    await ensure_playbook_schema(pool)
    await audit.record_required(
        pool,
        action="playbook.run_attempt",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="playbook",
        resource_id=str(playbook_id),
        details={"trigger_source": trigger_source},
    )

    # Idempotency is bound to the request that originally created the run, not
    # to the playbook's mutable current version. Resolve it before consulting
    # the current playbook so a valid replay remains valid after edits or
    # deactivation.
    existing = await _find_existing_run(
        pool,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        return await _resume_existing_run(
            pool,
            user=user,
            tenant_id=tenant_id,
            playbook_id=playbook_id,
            context=context,
            trigger_source=trigger_source,
            source_signal_id=source_signal_id,
            existing=existing,
        )

    playbook = await pool.fetchrow(
        """
        SELECT playbook.id::text, playbook.name, playbook.is_active,
               playbook.version,
               COALESCE(
                 jsonb_agg(
                   jsonb_build_object(
                     'key', action.id::text,
                     'playbook_action_id', action.id::text,
                     'action_type', action.action_type,
                     'configuration', action.configuration,
                     'sort_order', action.sort_order
                   ) ORDER BY action.sort_order, action.id
                 ) FILTER (WHERE action.id IS NOT NULL),
                 '[]'::jsonb
               ) AS action_plan_snapshot
        FROM playbooks AS playbook
        LEFT JOIN playbook_actions AS action ON action.playbook_id = playbook.id
        WHERE playbook.id = $1::uuid AND playbook.tenant_id = $2::uuid
        GROUP BY playbook.id, playbook.name, playbook.is_active, playbook.version
        """,
        str(playbook_id),
        str(tenant_id),
    )
    if playbook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook not found")
    if not playbook["is_active"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="playbook is inactive")
    action_plan = _normalize_action_plan(playbook.get("action_plan_snapshot", []))
    request_sha256 = _run_request_sha256(
        playbook_id=playbook_id,
        playbook_version=int(playbook["version"]),
        context=context,
        trigger_source=trigger_source,
        source_signal_id=source_signal_id,
        action_plan=action_plan,
    )
    row = await pool.fetchrow(
        """
        INSERT INTO playbook_runs (
            tenant_id, playbook_id, playbook_version, source_signal_id,
            idempotency_key, request_sha256,
            trigger_source, status, trigger_context, action_plan_snapshot,
            created_by_actor_id
        )
        VALUES (
            $1::uuid, $2::uuid, $3, $4::uuid, $5, $6,
            $7, 'running', $8::jsonb, $9::jsonb, $10::uuid
        )
        ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
        RETURNING id::text, playbook_id::text
        """,
        str(tenant_id),
        str(playbook_id),
        int(playbook["version"]),
        str(source_signal_id) if source_signal_id else None,
        idempotency_key,
        request_sha256,
        trigger_source,
        json.dumps(context),
        json.dumps(action_plan),
        user.user_id,
    )
    if row is None:
        existing = await _find_existing_run(
            pool,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
        )
        if existing is None:
            raise RuntimeError("idempotent playbook run could not be resolved")
        return await _resume_existing_run(
            pool,
            user=user,
            tenant_id=tenant_id,
            playbook_id=playbook_id,
            context=context,
            trigger_source=trigger_source,
            source_signal_id=source_signal_id,
            existing=existing,
        )

    run_id = UUID(row["id"])
    await audit.record_required(
        pool,
        action="playbook.run_started",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="playbook_run",
        resource_id=str(run_id),
        details={
            "playbook_id": str(playbook_id),
            "trigger_source": trigger_source,
            "source_signal_id": str(source_signal_id) if source_signal_id else None,
        },
    )
    await _execute_run_actions(
        pool,
        user=user,
        tenant_id=tenant_id,
        run_id=run_id,
        playbook_id=playbook_id,
    )
    result = await _fetch_run(pool, tenant_id=tenant_id, run_id=run_id)
    result["duplicate"] = False
    await audit.record_required(
        pool,
        action="playbook.run",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="playbook_run",
        resource_id=str(run_id),
        details={
            "playbook_id": str(playbook_id),
            "trigger_source": trigger_source,
            "status": result["status"],
            "source_signal_id": str(source_signal_id) if source_signal_id else None,
        },
    )
    return result


async def _find_existing_run(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    idempotency_key: str,
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT id::text, playbook_id::text, trigger_context, trigger_source,
               source_signal_id::text
        FROM playbook_runs
        WHERE tenant_id = $1::uuid AND idempotency_key = $2
        """,
        str(tenant_id),
        idempotency_key,
    )


async def _resume_existing_run(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    playbook_id: UUID,
    context: dict[str, Any],
    trigger_source: str,
    source_signal_id: UUID | None,
    existing: asyncpg.Record,
) -> dict[str, Any]:
    if existing["playbook_id"] != str(playbook_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="idempotency key is already used by a different playbook",
        )
    expected_signal_id = str(source_signal_id) if source_signal_id else None
    if (
        _json_object(existing["trigger_context"]) != context
        or existing["trigger_source"] != trigger_source
        or existing["source_signal_id"] != expected_signal_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="idempotency key was already used with a different playbook request",
        )
    existing_run_id = UUID(existing["id"])
    # Resume only the immutable stored plan. Existing plan keys guard every
    # already-started action from ambiguous side-effect repetition.
    await _execute_run_actions(
        pool,
        user=user,
        tenant_id=tenant_id,
        run_id=existing_run_id,
        playbook_id=playbook_id,
    )
    result = await _fetch_run(pool, tenant_id=tenant_id, run_id=existing_run_id)
    result["duplicate"] = True
    return result


async def run_matching_playbooks(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    context: dict[str, Any],
    idempotency_prefix: str,
    trigger_source: str,
    source_signal_id: UUID | None = None,
) -> list[dict[str, Any]]:
    await _authorize(pool, user=user, tenant_id=tenant_id, scope="playbooks:execute")
    await ensure_playbook_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, is_active, trigger_conditions
        FROM playbooks
        WHERE tenant_id = $1::uuid AND is_active = TRUE
        """,
        str(tenant_id),
    )
    results: list[dict[str, Any]] = []
    for row in rows:
        conditions = _json_object(row["trigger_conditions"])
        if not evaluate_playbook_trigger(
            is_active=bool(row["is_active"]),
            trigger_conditions=conditions,
            context=context,
        ):
            continue
        digest = hashlib.sha256(f"{idempotency_prefix}:{row['id']}".encode()).hexdigest()
        result = await execute_playbook(
            pool,
            user=user,
            tenant_id=tenant_id,
            playbook_id=UUID(row["id"]),
            idempotency_key=f"auto:{digest}",
            context=context,
            trigger_source=trigger_source,
            source_signal_id=source_signal_id,
        )
        results.append(result)
    return results


async def list_runs(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    playbook_id: UUID | None = None,
    source_signal_id: UUID | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    await _authorize(pool, user=user, tenant_id=tenant_id, scope="playbooks:read")
    await ensure_playbook_schema(pool)
    rows = await pool.fetch(
        """
        SELECT run.id::text, run.tenant_id::text, run.playbook_id::text,
               run.playbook_version,
               run.source_signal_id::text, run.idempotency_key, run.trigger_source,
               run.status, run.created_by_actor_id::text, run.created_at,
               run.updated_at, run.completed_at, playbook.name AS playbook_name
        FROM playbook_runs run
        JOIN playbooks playbook ON playbook.id = run.playbook_id
        WHERE run.tenant_id = $1::uuid
          AND ($2::uuid IS NULL OR run.playbook_id = $2::uuid)
          AND ($3::uuid IS NULL OR run.source_signal_id = $3::uuid)
        ORDER BY run.created_at DESC, run.id DESC
        LIMIT $4
        """,
        str(tenant_id),
        str(playbook_id) if playbook_id else None,
        str(source_signal_id) if source_signal_id else None,
        max(1, min(limit, 500)),
    )
    if not rows:
        return []
    run_ids = [row["id"] for row in rows]
    action_rows = await pool.fetch(
        """
        SELECT run_id::text, id::text, action_plan_key,
               playbook_action_id::text, action_type,
               status, attempt, max_attempts, status_code, error_code,
               external_reference, configuration_snapshot, result_metadata, next_attempt_at,
               last_attempt_at, created_at, updated_at, completed_at
        FROM playbook_action_results
        WHERE run_id = ANY($1::uuid[])
        ORDER BY run_id, created_at, id
        """,
        [UUID(item) for item in run_ids],
    )
    grouped: dict[str, list[asyncpg.Record]] = {run_id: [] for run_id in run_ids}
    for action in action_rows:
        grouped[action["run_id"]].append(action)
    return [_run_dict(row, grouped[row["id"]]) for row in rows]


async def acknowledge_action(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    run_id: UUID,
    action_result_id: UUID,
    succeeded: bool,
    external_reference: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    await _authorize(pool, user=user, tenant_id=tenant_id, scope="playbooks:execute")
    await ensure_playbook_schema(pool)
    new_status = "succeeded" if succeeded else "failed"
    updated = await pool.fetchrow(
        """
        WITH updated AS (
          UPDATE playbook_action_results AS result
          SET status = $4, external_reference = $5, result_metadata = $6::jsonb,
              updated_at = NOW(), completed_at = NOW()
          FROM playbook_runs AS run
          WHERE result.id = $1::uuid
            AND result.run_id = run.id
            AND run.id = $2::uuid
            AND run.tenant_id = $3::uuid
            AND result.status = 'awaiting_ack'
            AND result.action_type = ANY($7::text[])
          RETURNING result.id::text, result.status, run.playbook_id::text
        ), audit_receipt AS (
          INSERT INTO audit_events (
            actor_user_id, tenant_id, action, resource_type, resource_id, details
          )
          SELECT $8, $3::uuid, 'playbook.action_ack',
                 'playbook_action_result', updated.id,
                 jsonb_build_object('run_id', $2, 'status', $4)
          FROM updated
          RETURNING id
        )
        SELECT updated.*
        FROM updated CROSS JOIN audit_receipt
        """,
        str(action_result_id),
        str(run_id),
        str(tenant_id),
        new_status,
        external_reference,
        json.dumps(metadata),
        sorted(_CONTROL_PLANE_ACTIONS),
        user.actor_id,
    )
    duplicate = False
    if updated is None:
        current = await pool.fetchrow(
            """
            SELECT result.action_type, result.status, result.external_reference,
                   result.result_metadata, run.playbook_id::text
            FROM playbook_action_results AS result
            JOIN playbook_runs AS run ON run.id = result.run_id
            WHERE result.id = $1::uuid
              AND run.id = $2::uuid
              AND run.tenant_id = $3::uuid
            """,
            str(action_result_id),
            str(run_id),
            str(tenant_id),
        )
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="action result not found",
            )
        exact_replay = (
            current["action_type"] in _CONTROL_PLANE_ACTIONS
            and current["status"] == new_status
            and current["external_reference"] == external_reference
            and _json_object(current["result_metadata"]) == metadata
        )
        if not exact_replay:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="acknowledgement conflicts with the action's durable decision",
            )
        updated = current
        duplicate = True
    if succeeded:
        await _execute_run_actions(
            pool,
            user=user,
            tenant_id=tenant_id,
            run_id=run_id,
            playbook_id=UUID(updated["playbook_id"]),
        )
    else:
        await _refresh_run_status(pool, tenant_id=tenant_id, run_id=run_id)
    result = await _fetch_run(pool, tenant_id=tenant_id, run_id=run_id)
    result["ack_duplicate"] = duplicate
    return result


async def retry_action(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    run_id: UUID,
    action_result_id: UUID,
) -> dict[str, Any]:
    """Queue an operator-requested webhook retry without bypassing attempt bounds."""
    await _authorize(
        pool,
        user=user,
        tenant_id=tenant_id,
        scope="playbooks:execute",
        min_roles=frozenset({"owner", "admin"}),
    )
    await ensure_playbook_schema(pool)
    await audit.record_required(
        pool,
        action="playbook.action_retry_request_attempt",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="playbook_action_result",
        resource_id=str(action_result_id),
        details={"run_id": str(run_id)},
    )
    queued = await pool.fetchrow(
        """
        UPDATE playbook_action_results AS result
        SET status = 'retry_scheduled', next_attempt_at = NOW(),
            lease_owner = NULL, lease_expires_at = NULL,
            completed_at = NULL, updated_at = NOW()
        FROM playbook_runs AS run
        WHERE result.id = $1::uuid
          AND result.run_id = run.id
          AND run.id = $2::uuid
          AND run.tenant_id = $3::uuid
          AND result.action_type = 'webhook'
          AND result.status IN ('failed', 'retry_scheduled')
          AND result.attempt < result.max_attempts
        RETURNING result.id::text, result.attempt, result.max_attempts
        """,
        str(action_result_id),
        str(run_id),
        str(tenant_id),
    )
    if queued is None:
        current = await pool.fetchrow(
            """
            SELECT result.action_type, result.status, result.attempt, result.max_attempts
            FROM playbook_action_results AS result
            JOIN playbook_runs AS run ON run.id = result.run_id
            WHERE result.id = $1::uuid
              AND run.id = $2::uuid
              AND run.tenant_id = $3::uuid
            """,
            str(action_result_id),
            str(run_id),
            str(tenant_id),
        )
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="action result not found",
            )
        if current["action_type"] != "webhook":
            detail = "control-plane actions must use acknowledgement, not retry"
        elif current["status"] in {"running", "succeeded", "awaiting_ack"}:
            detail = f"action in {current['status']} state cannot be retried"
        elif int(current["attempt"]) >= int(current["max_attempts"]):
            detail = "action retry attempts are exhausted"
        else:
            detail = "action is not eligible for retry"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    await _refresh_run_status(pool, tenant_id=tenant_id, run_id=run_id)
    await audit.record_required(
        pool,
        action="playbook.action_retry_requested",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="playbook_action_result",
        resource_id=str(action_result_id),
        details={
            "run_id": str(run_id),
            "attempt": int(queued["attempt"]),
            "max_attempts": int(queued["max_attempts"]),
        },
    )
    return await _fetch_run(pool, tenant_id=tenant_id, run_id=run_id)


async def tick_playbook_retries(
    pool: asyncpg.Pool,
    *,
    batch_size: int = 50,
    worker_id: str | None = None,
    _schema_ready: bool = False,
    health: WorkerHealthRegistry | None = None,
) -> dict[str, int | bool]:
    """Claim and execute one bounded batch of due webhook retries."""
    if not _schema_ready:
        await ensure_playbook_schema(pool)
    owner = (worker_id or f"soar:{uuid4()}")[:128]
    limit = max(1, min(int(batch_size), 200))

    exhausted = await _finalize_expired_retry_leases(pool)
    for exhausted_row in exhausted:
        tenant_text = str(exhausted_row["tenant_id"])
        run_text = str(exhausted_row["run_id"])
        await audit.record_required(
            pool,
            action="playbook.action_retry_exhausted",
            tenant_id=tenant_text,
            resource_type="playbook_action_result",
            resource_id=str(exhausted_row["id"]),
            details={
                "run_id": run_text,
                "attempt": int(exhausted_row["attempt"]),
                "reason": "expired_final_lease",
            },
        )
        await _refresh_run_status(
            pool,
            tenant_id=UUID(tenant_text),
            run_id=UUID(run_text),
        )

    counts = {
        "ok": True,
        "claimed": 0,
        "succeeded": 0,
        "rescheduled": 0,
        "failed": 0,
        "lease_lost": 0,
        "exhausted": len(exhausted),
    }
    # Claim immediately before delivery. A slow upstream can no longer consume
    # most of the lease time for later rows in a pre-claimed batch.
    for _ in range(limit):
        claimed = await _claim_due_webhook_retries(
            pool,
            batch_size=1,
            worker_id=owner,
        )
        if not claimed:
            break
        row = claimed[0]
        counts["claimed"] += 1
        tenant_id = UUID(str(row["tenant_id"]))
        run_id = UUID(str(row["run_id"]))
        action_result_id = UUID(str(row["id"]))
        await audit.record_required(
            pool,
            action="playbook.action_attempt",
            tenant_id=tenant_id,
            resource_type="playbook_action_result",
            resource_id=str(action_result_id),
            details={
                "run_id": str(run_id),
                "action_type": "webhook",
                "attempt": int(row["attempt"]),
                "max_attempts": int(row["max_attempts"]),
            },
        )
        outcome = await _run_webhook(
            _json_object(row["configuration_snapshot"]),
            _json_object(row["trigger_context"]),
            run_id=run_id,
            action_result_id=action_result_id,
        )
        durable = await _persist_webhook_outcome(
            pool,
            tenant_id=tenant_id,
            run_id=run_id,
            action_result_id=action_result_id,
            lease_owner=owner,
            attempt=int(row["attempt"]),
            max_attempts=int(row["max_attempts"]),
            outcome=outcome,
            actor_user_id=(
                str(row["created_by_actor_id"])
                if row.get("created_by_actor_id") is not None
                else None
            ),
            audit_action="playbook.action_retry",
        )
        if not durable["persisted"]:
            counts["lease_lost"] += 1
            continue

        durable_status = str(durable["status"])
        if durable_status == "succeeded":
            counts["succeeded"] += 1
        elif durable_status == "retry_scheduled":
            counts["rescheduled"] += 1
        else:
            counts["failed"] += 1
        if durable_status == "succeeded":
            await _execute_run_actions(
                pool,
                user=None,
                tenant_id=tenant_id,
                run_id=run_id,
                playbook_id=UUID(str(row["playbook_id"])),
            )
        else:
            await _refresh_run_status(pool, tenant_id=tenant_id, run_id=run_id)
        if health is not None:
            health.succeeded("soar-retries")
    return counts


async def run_playbook_retry_worker(
    pool: asyncpg.Pool,
    stop_event: asyncio.Event,
    *,
    interval_seconds: float = 5.0,
    batch_size: int = 50,
    health: WorkerHealthRegistry | None = None,
) -> None:
    """Continuously run retry ticks until the application lifespan stops."""
    schema_ready = False
    worker_id = f"soar:{uuid4()}"
    interval = max(1.0, min(float(interval_seconds), 60.0))
    while not stop_event.is_set():
        tick_errors: list[Exception] = []
        try:
            if not schema_ready:
                await ensure_playbook_schema(pool)
                schema_ready = True
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            tick_errors.append(exc)
            logger.warning("SOAR schema readiness failed error_type=%s", type(exc).__name__)
        if schema_ready:
            try:
                retry_summary = await tick_playbook_retries(
                    pool,
                    batch_size=batch_size,
                    worker_id=worker_id,
                    _schema_ready=True,
                    health=health,
                )
                if int(retry_summary.get("lease_lost") or 0):
                    tick_errors.append(RuntimeError("SOAR retry lease was lost"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                tick_errors.append(exc)
                logger.warning("SOAR retry worker tick failed error_type=%s", type(exc).__name__)
            try:
                continuation_summary = await tick_playbook_continuations(
                    pool,
                    batch_size=batch_size,
                    _schema_ready=True,
                    health=health,
                )
                if int(continuation_summary.get("failed") or 0):
                    tick_errors.append(RuntimeError("SOAR continuation reconciliation failed"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                tick_errors.append(exc)
                logger.warning(
                    "SOAR continuation worker tick failed error_type=%s",
                    type(exc).__name__,
                )
        if health is not None:
            if tick_errors:
                health.failed("soar-retries", tick_errors[-1])
            elif schema_ready:
                health.succeeded("soar-retries")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval)


async def tick_playbook_continuations(
    pool: asyncpg.Pool,
    *,
    batch_size: int = 50,
    _schema_ready: bool = False,
    health: WorkerHealthRegistry | None = None,
) -> dict[str, int | bool]:
    """Resume nonterminal runs that have no action currently holding the baton."""
    if not _schema_ready:
        await ensure_playbook_schema(pool)
    rows = await pool.fetch(
        """
        SELECT run.id::text, run.tenant_id::text, run.playbook_id::text
        FROM playbook_runs AS run
        WHERE run.status IN ('running', 'retrying', 'awaiting_ack')
          AND NOT EXISTS (
            SELECT 1
            FROM playbook_action_results AS result
            WHERE result.run_id = run.id
              AND result.status IN ('running', 'retry_scheduled', 'awaiting_ack')
          )
        ORDER BY run.updated_at, run.id
        LIMIT $1
        """,
        max(1, min(int(batch_size), 200)),
    )
    counts = {"ok": True, "eligible": len(rows), "resumed": 0, "failed": 0}
    for row in rows:
        try:
            await _execute_run_actions(
                pool,
                user=None,
                tenant_id=UUID(str(row["tenant_id"])),
                run_id=UUID(str(row["id"])),
                playbook_id=UUID(str(row["playbook_id"])),
            )
            counts["resumed"] += 1
            if health is not None:
                health.succeeded("soar-retries")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            counts["failed"] += 1
            logger.warning(
                "SOAR continuation reconciliation failed run_id=%s error_type=%s",
                row["id"],
                type(exc).__name__,
            )
    return counts


async def _claim_due_webhook_retries(
    pool: asyncpg.Pool,
    *,
    batch_size: int,
    worker_id: str,
) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        WITH due AS MATERIALIZED (
          SELECT result.id, run.tenant_id, run.playbook_id, run.trigger_context,
                 run.created_by_actor_id
          FROM playbook_action_results AS result
          JOIN playbook_runs AS run ON run.id = result.run_id
          WHERE result.action_type = 'webhook'
            AND result.attempt < result.max_attempts
            AND (
              (
                result.status = 'retry_scheduled'
                AND result.next_attempt_at <= NOW()
                AND (
                  result.lease_expires_at IS NULL
                  OR result.lease_expires_at <= NOW()
                )
              )
              OR (
                result.status = 'running'
                AND result.lease_expires_at IS NOT NULL
                AND result.lease_expires_at <= NOW()
              )
            )
          ORDER BY COALESCE(result.next_attempt_at, result.lease_expires_at),
                   result.created_at, result.id
          LIMIT $1
          FOR UPDATE OF result SKIP LOCKED
        ), claimed AS (
          UPDATE playbook_action_results AS result
          SET status = 'running', attempt = result.attempt + 1,
              last_attempt_at = NOW(), next_attempt_at = NULL,
              lease_owner = $2,
              lease_expires_at = NOW() + ($3 * INTERVAL '1 second'),
              completed_at = NULL, updated_at = NOW()
          FROM due
          WHERE result.id = due.id
          RETURNING result.id::text, result.run_id::text, result.attempt,
                    result.max_attempts, result.configuration_snapshot
        )
        SELECT claimed.*, due.tenant_id::text, due.playbook_id::text,
               due.trigger_context, due.created_by_actor_id::text
        FROM claimed
        JOIN due ON due.id = claimed.id::uuid
        """,
        batch_size,
        worker_id,
        _WEBHOOK_LEASE_SECONDS,
    )


async def _finalize_expired_retry_leases(
    pool: asyncpg.Pool,
) -> list[asyncpg.Record]:
    rows = await pool.fetch(
        """
        UPDATE playbook_action_results AS result
        SET status = 'failed',
            error_code = COALESCE(result.error_code, 'retry_lease_expired'),
            result_metadata = result.result_metadata
              || '{"retry_exhausted": true, "delivery_outcome_unknown": true}'::jsonb,
            next_attempt_at = NULL, lease_owner = NULL, lease_expires_at = NULL,
            updated_at = NOW(), completed_at = NOW()
        FROM playbook_runs AS run
        WHERE result.run_id = run.id
          AND result.action_type = 'webhook'
          AND result.status = 'running'
          AND result.attempt >= result.max_attempts
          AND result.lease_expires_at IS NOT NULL
          AND result.lease_expires_at <= NOW()
        RETURNING result.id::text, result.attempt,
                  run.tenant_id::text AS tenant_id, run.id::text AS run_id
        """
    )
    return list(rows)


async def _execute_run_actions(
    pool: asyncpg.Pool,
    *,
    user: AuthUser | None,
    tenant_id: UUID,
    run_id: UUID,
    playbook_id: UUID,
) -> None:
    run_snapshot = await pool.fetchrow(
        """
        SELECT action_plan_snapshot, trigger_context, created_by_actor_id::text
        FROM playbook_runs
        WHERE id = $1::uuid AND tenant_id = $2::uuid AND playbook_id = $3::uuid
        """,
        str(run_id),
        str(tenant_id),
        str(playbook_id),
    )
    if run_snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook run not found")
    actions = _normalize_action_plan(run_snapshot["action_plan_snapshot"])
    context = _json_object(run_snapshot["trigger_context"])
    stored_actor_id = run_snapshot.get("created_by_actor_id")
    actor_user_id = (
        user.actor_id
        if user is not None
        else (str(stored_actor_id) if stored_actor_id is not None else None)
    )
    for action in actions:
        action_type = str(action["action_type"])
        configuration = _json_object(action["configuration"])
        action_result_id = uuid4()
        lease_owner = f"initial:{uuid4()}" if action_type == "webhook" else None
        if action_type == "webhook":
            initial_status = "running"
            initial_metadata: dict[str, Any] = {}
            max_attempts = _WEBHOOK_MAX_ATTEMPTS
            completed = False
        elif action_type in _CONTROL_PLANE_ACTIONS:
            initial_status = "awaiting_ack"
            initial_metadata = {"reason": "control_plane_ack_required"}
            max_attempts = 1
            completed = False
        else:
            initial_status = "unsupported"
            initial_metadata = {}
            max_attempts = 1
            completed = True
        result_row = await pool.fetchrow(
            """
            INSERT INTO playbook_action_results (
                id, run_id, action_plan_key, playbook_action_id, action_type, status,
                max_attempts, configuration_snapshot, result_metadata,
                last_attempt_at, lease_owner, lease_expires_at, completed_at
            )
            VALUES (
                $1::uuid, $2::uuid, $3,
                (SELECT id FROM playbook_actions WHERE id = $4::uuid),
                $5, $6, $7, $8::jsonb, $9::jsonb,
                CASE WHEN $5 = 'webhook' THEN NOW() ELSE NULL END,
                $10,
                CASE WHEN $10::text IS NULL THEN NULL
                     ELSE NOW() + ($11 * INTERVAL '1 second') END,
                CASE WHEN $12 THEN NOW() ELSE NULL END
            )
            ON CONFLICT (run_id, action_plan_key) DO NOTHING
            RETURNING id::text
            """,
            str(action_result_id),
            str(run_id),
            action["key"],
            action.get("playbook_action_id"),
            action_type,
            initial_status,
            max_attempts,
            json.dumps(configuration),
            json.dumps(initial_metadata),
            lease_owner,
            _WEBHOOK_LEASE_SECONDS,
            completed,
        )
        if result_row is None:
            existing_status = await pool.fetchval(
                """
                SELECT status FROM playbook_action_results
                WHERE run_id = $1::uuid AND action_plan_key = $2
                """,
                str(run_id),
                action["key"],
            )
            if existing_status != "succeeded":
                break
            continue
        action_result_id = UUID(str(result_row["id"]))
        durable_status = initial_status
        attempt = 1
        if action_type == "webhook":
            await audit.record_required(
                pool,
                action="playbook.action_attempt",
                actor_user_id=actor_user_id,
                tenant_id=tenant_id,
                resource_type="playbook_action_result",
                resource_id=str(action_result_id),
                details={
                    "run_id": str(run_id),
                    "action_type": action_type,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                },
            )
            outcome = await _run_webhook(
                configuration,
                context,
                run_id=run_id,
                action_result_id=action_result_id,
            )
            durable = await _persist_webhook_outcome(
                pool,
                tenant_id=tenant_id,
                run_id=run_id,
                action_result_id=action_result_id,
                lease_owner=str(lease_owner),
                attempt=attempt,
                max_attempts=max_attempts,
                outcome=outcome,
                actor_user_id=actor_user_id,
                audit_action="playbook.action_result",
            )
            if not durable["persisted"]:
                logger.warning(
                    "initial webhook result lease lost action_result_id=%s", action_result_id
                )
                break
            durable_status = str(durable["status"])
        else:
            await audit.record_required(
                pool,
                action="playbook.action_result",
                actor_user_id=actor_user_id,
                tenant_id=tenant_id,
                resource_type="playbook_action_result",
                resource_id=str(action_result_id),
                details={
                    "run_id": str(run_id),
                    "action_type": action_type,
                    "status": durable_status,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                },
            )
        if durable_status != "succeeded":
            break
    await _refresh_run_status(pool, tenant_id=tenant_id, run_id=run_id)


async def _persist_webhook_outcome(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    run_id: UUID,
    action_result_id: UUID,
    lease_owner: str,
    attempt: int,
    max_attempts: int,
    outcome: dict[str, Any],
    actor_user_id: str | None,
    audit_action: str,
) -> dict[str, Any]:
    durable = _durable_webhook_outcome(
        outcome,
        attempt=attempt,
        max_attempts=max_attempts,
    )
    row = await pool.fetchrow(
        """
        WITH updated AS (
          UPDATE playbook_action_results AS result
          SET status = $4, status_code = $5, error_code = $6,
              result_metadata = $7::jsonb,
              next_attempt_at = CASE
                WHEN $4 = 'retry_scheduled'
                  THEN NOW() + ($8 * INTERVAL '1 second')
                ELSE NULL
              END,
              lease_owner = NULL, lease_expires_at = NULL,
              updated_at = NOW(),
              completed_at = CASE
                WHEN $4 IN ('succeeded', 'failed', 'unsupported') THEN NOW()
                ELSE NULL
              END
          WHERE result.id = $1::uuid AND result.run_id = $2::uuid
            AND result.lease_owner = $3 AND result.status = 'running'
          RETURNING result.id::text, result.action_type, result.status,
                    result.attempt, result.max_attempts
        ), audit_receipt AS (
          INSERT INTO audit_events (
            actor_user_id, tenant_id, action, resource_type, resource_id, details
          )
          SELECT $9, $10::uuid, $11, 'playbook_action_result', updated.id,
                 jsonb_build_object(
                   'run_id', $2,
                   'action_type', updated.action_type,
                   'status', updated.status,
                   'attempt', updated.attempt,
                   'max_attempts', updated.max_attempts
                 )
          FROM updated
          RETURNING id
        )
        SELECT updated.status
        FROM updated CROSS JOIN audit_receipt
        """,
        str(action_result_id),
        str(run_id),
        lease_owner,
        durable["status"],
        durable["status_code"],
        durable["error_code"],
        json.dumps(durable["metadata"]),
        int(durable.get("retry_after_seconds") or 0),
        actor_user_id,
        str(tenant_id),
        audit_action,
    )
    return {**durable, "persisted": row is not None}


def _durable_webhook_outcome(
    outcome: dict[str, Any],
    *,
    attempt: int,
    max_attempts: int,
) -> dict[str, Any]:
    durable = {
        "status": str(outcome["status"]),
        "status_code": outcome.get("status_code"),
        "error_code": outcome.get("error_code"),
        "metadata": dict(outcome.get("metadata") or {}),
        "retry_after_seconds": None,
    }
    if durable["status"] != "failed" or not bool(outcome.get("retryable")):
        return durable
    if attempt >= max_attempts:
        durable["metadata"]["retry_exhausted"] = True
        return durable
    delay = _retry_backoff_seconds(
        attempt,
        retry_after_seconds=outcome.get("retry_after_seconds"),
    )
    durable["status"] = "retry_scheduled"
    durable["metadata"]["retryable"] = True
    durable["metadata"]["retry_after_seconds"] = delay
    durable["retry_after_seconds"] = delay
    return durable


def _retry_backoff_seconds(
    attempt: int,
    *,
    retry_after_seconds: int | None = None,
) -> int:
    exponent = max(0, min(int(attempt) - 1, 10))
    delay = min(_WEBHOOK_RETRY_CAP_SECONDS, _WEBHOOK_RETRY_BASE_SECONDS * (2**exponent))
    if retry_after_seconds is not None:
        delay = max(delay, min(max(0, int(retry_after_seconds)), _WEBHOOK_RETRY_CAP_SECONDS))
    return min(delay, _WEBHOOK_RETRY_CAP_SECONDS)


def _parse_retry_after(value: str | None, *, now: datetime | None = None) -> int | None:
    if not value:
        return None
    clean = value.strip()
    if not clean:
        return None
    try:
        seconds = int(clean)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(clean)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        current = now or datetime.now(UTC)
        seconds = math.ceil((parsed.astimezone(UTC) - current.astimezone(UTC)).total_seconds())
    return min(max(0, seconds), _WEBHOOK_RETRY_CAP_SECONDS)


def _is_retryable_webhook_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_WEBHOOK_STATUS_CODES or 500 <= status_code < 600


async def _run_webhook(
    configuration: dict[str, Any],
    context: dict[str, Any],
    *,
    run_id: UUID,
    action_result_id: UUID,
) -> dict[str, Any]:
    url = str(configuration.get("url") or "").strip()
    if not url:
        return {
            "status": "failed",
            "status_code": None,
            "error_code": "invalid_configuration",
            "metadata": {},
            "retryable": False,
            "retry_after_seconds": None,
        }
    try:
        signing_key = _webhook_signing_secret(configuration)
    except ValueError:
        # Stored references can outlive a deployment secret. Fail truthfully
        # and permanently without emitting an unsigned request.
        return {
            "status": "failed",
            "status_code": None,
            "error_code": "signing_secret_unavailable",
            "metadata": {},
            "retryable": False,
            "retry_after_seconds": None,
        }
    try:
        safe_url = await validate_outbound_url(url, purpose="webhook")
        timeout = httpx.Timeout(10.0, connect=3.0, read=5.0, write=5.0, pool=3.0)
        limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
        payload_bytes = json.dumps(
            {"context": context, "source": "forjd-playbook"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-FORJD-Run-ID": str(run_id),
            "X-FORJD-Action-ID": str(action_result_id),
            "Idempotency-Key": f"{run_id}:{action_result_id}",
        }
        if signing_key is not None:
            secret_ref, secret = signing_key
            timestamp = str(int(datetime.now(UTC).timestamp()))
            signature = hmac.new(
                secret,
                timestamp.encode("ascii") + b"." + payload_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers.update(
                {
                    "X-FORJD-Timestamp": timestamp,
                    "X-FORJD-Key-ID": secret_ref,
                    "X-FORJD-Signature": f"v1={signature}",
                }
            )
        async with (
            httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                follow_redirects=False,
            ) as client,
            client.stream(
                "POST",
                safe_url,
                headers=headers,
                content=payload_bytes,
            ) as response,
        ):
            code = response.status_code
            response_headers = getattr(response, "headers", {})
            retry_after_value = (
                response_headers.get("Retry-After") if hasattr(response_headers, "get") else None
            )
        if 200 <= code < 300:
            return {
                "status": "succeeded",
                "status_code": code,
                "error_code": None,
                "metadata": {},
                "retryable": False,
                "retry_after_seconds": None,
            }
        retryable = _is_retryable_webhook_status(code)
        if 300 <= code < 400:
            error_code = "redirect_rejected"
        elif code == 429:
            error_code = "rate_limited"
        elif code == 408:
            error_code = "request_timeout"
        elif code == 425:
            error_code = "too_early"
        elif 500 <= code < 600:
            error_code = "upstream_error"
        else:
            error_code = "http_error"
        return {
            "status": "failed",
            "status_code": code,
            "error_code": error_code,
            "metadata": {},
            "retryable": retryable,
            "retry_after_seconds": (_parse_retry_after(retry_after_value) if retryable else None),
        }
    except ValueError as exc:
        resolution_failure = isinstance(exc.__cause__, (OSError, TimeoutError))
        return {
            "status": "failed",
            "status_code": None,
            "error_code": "network_error" if resolution_failure else "destination_rejected",
            "metadata": {},
            "retryable": resolution_failure,
            "retry_after_seconds": None,
        }
    except (httpx.HTTPError, OSError, TimeoutError) as exc:
        logger.warning("playbook webhook failed error_type=%s", type(exc).__name__)
        return {
            "status": "failed",
            "status_code": None,
            "error_code": "network_error",
            "metadata": {},
            "retryable": True,
            "retry_after_seconds": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("playbook webhook execution error error_type=%s", type(exc).__name__)
        return {
            "status": "failed",
            "status_code": None,
            "error_code": "execution_error",
            "metadata": {},
            "retryable": False,
            "retry_after_seconds": None,
        }


def summarize_action_statuses(statuses: list[str]) -> str:
    """Collapse durable action states into the run state."""
    if not statuses:
        return "succeeded"
    values = set(statuses)
    if "running" in values:
        return "running"
    if "retry_scheduled" in values:
        return "retrying"
    if "awaiting_ack" in values:
        return "awaiting_ack"
    if values == {"succeeded"}:
        return "succeeded"
    if values == {"unsupported"}:
        return "unsupported"
    if values == {"failed"}:
        return "failed"
    return "partial"


def _run_request_sha256(
    *,
    playbook_id: UUID,
    playbook_version: int,
    context: dict[str, Any],
    trigger_source: str,
    source_signal_id: UUID | None,
    action_plan: list[dict[str, Any]] | None = None,
) -> str:
    canonical = json.dumps(
        {
            "playbook_id": str(playbook_id),
            "playbook_version": playbook_version,
            "context": context,
            "trigger_source": trigger_source,
            "source_signal_id": str(source_signal_id) if source_signal_id else None,
            "action_plan": action_plan or [],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _refresh_run_status(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    run_id: UUID,
) -> str:
    rows = await pool.fetch(
        """
        SELECT result.status
        FROM playbook_action_results result
        JOIN playbook_runs run ON run.id = result.run_id
        WHERE run.id = $1::uuid AND run.tenant_id = $2::uuid
        """,
        str(run_id),
        str(tenant_id),
    )
    run_status = summarize_action_statuses([str(row["status"]) for row in rows])
    complete = run_status not in {"running", "retrying", "awaiting_ack"}
    await pool.execute(
        """
        UPDATE playbook_runs
        SET status = $3, updated_at = NOW(),
            completed_at = CASE WHEN $4 THEN COALESCE(completed_at, NOW()) ELSE NULL END
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        """,
        str(run_id),
        str(tenant_id),
        run_status,
        complete,
    )
    return run_status


async def _fetch_run(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    run_id: UUID,
) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        SELECT run.id::text, run.tenant_id::text, run.playbook_id::text,
               run.playbook_version,
               run.source_signal_id::text, run.idempotency_key, run.trigger_source,
               run.status, run.created_by_actor_id::text, run.created_at,
               run.updated_at, run.completed_at, playbook.name AS playbook_name
        FROM playbook_runs run
        JOIN playbooks playbook ON playbook.id = run.playbook_id
        WHERE run.id = $1::uuid AND run.tenant_id = $2::uuid
        """,
        str(run_id),
        str(tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook run not found")
    action_rows = await pool.fetch(
        """
        SELECT id::text, action_plan_key, playbook_action_id::text,
               action_type, status, attempt,
               max_attempts, status_code, error_code, external_reference,
               configuration_snapshot, result_metadata, next_attempt_at, last_attempt_at,
               created_at, updated_at, completed_at
        FROM playbook_action_results
        WHERE run_id = $1::uuid
        ORDER BY created_at, id
        """,
        str(run_id),
    )
    return _run_dict(row, action_rows)


def _run_dict(row: asyncpg.Record, action_rows: list[asyncpg.Record]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "playbook_id": row["playbook_id"],
        "playbook_version": int(row["playbook_version"]),
        "playbook_name": row["playbook_name"],
        "source_signal_id": row["source_signal_id"],
        "idempotency_key": row["idempotency_key"],
        "trigger_source": row["trigger_source"],
        "status": row["status"],
        "created_by_actor_id": row["created_by_actor_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "actions": [_action_result_dict(item) for item in action_rows],
    }


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _normalize_action_plan(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="playbook action plan is invalid",
            ) from exc
    if not isinstance(value, list) or len(value) > 50:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="playbook action plan is invalid",
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ordinal, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="playbook action plan is invalid",
            )
        action_type = str(raw.get("action_type") or "")[:64]
        key = str(raw.get("key") or raw.get("playbook_action_id") or f"plan:{ordinal}")
        if not action_type or not (1 <= len(key) <= 128) or key in seen:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="playbook action plan is invalid",
            )
        seen.add(key)
        raw_configuration = _json_object(raw.get("configuration"))
        allowed_keys = _ACTION_CONFIGURATION_KEYS.get(action_type, frozenset())
        configuration = {
            item_key: item_value
            for item_key, item_value in raw_configuration.items()
            if item_key in allowed_keys
        }
        playbook_action_id = raw.get("playbook_action_id")
        try:
            playbook_action_id = str(UUID(str(playbook_action_id)))
        except (TypeError, ValueError, AttributeError):
            playbook_action_id = None
        normalized.append(
            {
                "key": key,
                "playbook_action_id": playbook_action_id,
                "action_type": action_type,
                "configuration": configuration,
                "sort_order": int(raw.get("sort_order", ordinal)),
            }
        )
    return normalized


def _action_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "action_type": row["action_type"],
        "configuration": _json_object(row["configuration"]),
        "sort_order": row["sort_order"],
    }


def _action_result_dict(row: asyncpg.Record) -> dict[str, Any]:
    action_type = str(row["action_type"])
    result = {
        "id": row["id"],
        "action_plan_key": row["action_plan_key"],
        "playbook_action_id": row["playbook_action_id"],
        "action_type": action_type,
        "status": row["status"],
        "attempt": row["attempt"],
        "max_attempts": row["max_attempts"],
        "status_code": row["status_code"],
        "error_code": row["error_code"],
        "external_reference": row["external_reference"],
        "metadata": _json_object(row["result_metadata"]),
        "next_attempt_at": row["next_attempt_at"],
        "last_attempt_at": row["last_attempt_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
    }
    if action_type in _CONTROL_PLANE_ACTIONS:
        raw_configuration = _json_object(row.get("configuration_snapshot"))
        allowed_keys = _ACTION_CONFIGURATION_KEYS[action_type]
        result["configuration"] = {
            key: value for key, value in raw_configuration.items() if key in allowed_keys
        }
    return result


def _playbook_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "name": row["name"],
        "description": row["description"],
        "is_active": bool(row["is_active"]),
        "trigger_conditions": _json_object(row["trigger_conditions"]),
        "version": int(row["version"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
