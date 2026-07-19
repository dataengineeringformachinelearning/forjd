"""Tenant membership helpers (service-role DB access after principal verification).

Humans: `tenant_members` role check.
Services: hard-bound to one `tenant_id` + capability scopes (see sql/014).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status

from app.core.auth import AuthUser, PrincipalKind
from app.core.config import settings
from app.core.request_context import bind_principal_context

logger = logging.getLogger("forjd.tenants")

# Every migrated tenant/security table must exist with RLS when REQUIRE_RLS is
# set. Keeping this exhaustive prevents a feature-specific ensure_* helper from
# silently creating an unconstrained table after readiness already passed.
_RLS_TABLES = (
    "aggregated_analytics",
    "assets",
    "audit_events",
    "crypto_sessions",
    "correlation_receipts",
    "daemon_api_keys",
    "discovered_endpoints",
    "embedding_vectors",
    "endpoint_observations",
    "export_jobs",
    "health_probe_observations",
    "honeypot_endpoints",
    "honeypot_interactions",
    "incident_cases",
    "ingest_processing_batches",
    "lighthouse_scans",
    "ml_scores",
    "outbox_events",
    "playbook_action_results",
    "playbook_actions",
    "playbook_runs",
    "playbooks",
    "projection_checkpoints",
    "projection_dlq",
    "report_archives",
    "report_documents",
    "scheduled_task_runs",
    "security_signals",
    "service_accounts",
    "status_incidents",
    "status_pages",
    "status_services",
    "stream_results",
    "telemetry_events",
    "telemetry_ingest_receipts",
    "tenant_erase_receipts",
    "tenant_members",
    "tenants",
    "threat_intelligence",
    "threat_reports",
    "training_runs",
    "use_cases",
    "validated_sites",
    "vulnerabilities",
    "web_technology_observations",
)

# Cache only successful work for the lifetime of a concrete pool. The pool
# object is retained alongside its id so Python id reuse cannot inherit a prior
# result. Tests and lifecycle code can invalidate explicitly.
_SCHEMA_SUCCESS: dict[tuple[int, str, bool, bool], object] = {}
_SCHEMA_LOCKS: dict[tuple[int, str, bool, bool], tuple[object, asyncio.Lock]] = {}


# --- Schema readiness (fail closed in production) ---
async def _assert_secure_schema_uncached(pool: asyncpg.Pool) -> None:
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
            "secure schema incomplete — apply every migration in backend/sql; missing: "
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
        raise RuntimeError("RLS required but disabled on: " + ", ".join(no_rls))


# --- Local soft-migrate (shapes only; full RLS needs sql/003–019) ---
async def _ensure_secure_schema_uncached(pool: asyncpg.Pool) -> None:
    """Ensure schema for local/dev; production asserts migrations + RLS.

    Soft-migrate creates table shapes without policies — never used when
    ENVIRONMENT=production (SOFT_MIGRATE_SCHEMA forced false).
    """
    if not settings.SOFT_MIGRATE_SCHEMA:
        await _assert_secure_schema_uncached(pool)
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
    await pool.execute("ALTER TABLE telemetry_events ADD COLUMN IF NOT EXISTS event_type TEXT")
    await pool.execute("ALTER TABLE telemetry_events ADD COLUMN IF NOT EXISTS workflow_id TEXT")
    await pool.execute("ALTER TABLE telemetry_events ADD COLUMN IF NOT EXISTS ciphertext_bytes INT")
    await pool.execute(
        "ALTER TABLE telemetry_events ADD COLUMN IF NOT EXISTS ingest_fingerprint TEXT"
    )
    await pool.execute(
        """
        UPDATE telemetry_events
        SET ciphertext_bytes = octet_length(decode(ciphertext, 'base64'))
        WHERE ciphertext_bytes IS NULL
        """
    )
    await pool.execute("ALTER TABLE telemetry_events ALTER COLUMN ciphertext_bytes SET NOT NULL")
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
    await pool.execute("ALTER TABLE stream_results ADD COLUMN IF NOT EXISTS workflow_id TEXT")
    await pool.execute("ALTER TABLE stream_results ADD COLUMN IF NOT EXISTS projection_name TEXT")
    await pool.execute("ALTER TABLE stream_results ADD COLUMN IF NOT EXISTS source_event_id UUID")
    await pool.execute(
        """
        ALTER TABLE stream_results
        ADD COLUMN IF NOT EXISTS projection_version INT NOT NULL DEFAULT 1
        """
    )
    await pool.execute(
        "ALTER TABLE stream_results ADD COLUMN IF NOT EXISTS projection_result_key TEXT"
    )
    await pool.execute(
        """
        UPDATE stream_results
        SET projection_name = COALESCE(
          NULLIF(projection_name, ''),
          NULLIF(metadata ->> 'projection_name', ''),
          'sealed.default'
        )
        WHERE projection_name IS NULL OR projection_name = ''
        """
    )
    await pool.execute("ALTER TABLE stream_results ALTER COLUMN projection_name SET NOT NULL")
    await pool.execute(
        """
        UPDATE stream_results
        SET projection_result_key = encode(digest(id::text, 'sha256'), 'hex')
        WHERE projection_result_key IS NULL
        """
    )
    await pool.execute("ALTER TABLE stream_results ALTER COLUMN projection_result_key SET NOT NULL")
    await pool.execute("DROP INDEX IF EXISTS stream_results_proj_idem_uidx")
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS stream_results_projection_result_uidx
          ON stream_results (
            tenant_id, projection_name, projection_version, projection_result_key
          )
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
            revoked_at TIMESTAMPTZ,
            UNIQUE (tenant_id, session_id)
        )
        """
    )
    await pool.execute(
        "ALTER TABLE crypto_sessions ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ"
    )
    # Nonce reuse guard (sql/013); soft-migrate for local/dev.
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS telemetry_events_tenant_key_nonce_uidx
          ON telemetry_events (tenant_id, key_id, nonce)
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
            projection_version INT NOT NULL DEFAULT 1
                CHECK (projection_version >= 1),
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
        ALTER TABLE projection_dlq
        ADD COLUMN IF NOT EXISTS projection_version INT NOT NULL DEFAULT 1
        """
    )
    await pool.execute("ALTER TABLE projection_dlq ADD COLUMN IF NOT EXISTS dedupe_key TEXT")
    await pool.execute(
        """
        ALTER TABLE projection_dlq
        ADD COLUMN IF NOT EXISTS error_class TEXT NOT NULL DEFAULT 'processing_error'
        """
    )
    await pool.execute(
        "ALTER TABLE projection_dlq ADD COLUMN IF NOT EXISTS max_attempts INT NOT NULL DEFAULT 10"
    )
    await pool.execute(
        """
        ALTER TABLE projection_dlq
        ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        """
    )
    await pool.execute(
        "ALTER TABLE projection_dlq ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ"
    )
    await pool.execute("ALTER TABLE projection_dlq ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ")
    await pool.execute("ALTER TABLE projection_dlq ADD COLUMN IF NOT EXISTS locked_by TEXT")
    await pool.execute(
        "ALTER TABLE projection_dlq ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ"
    )
    await pool.execute(
        """
        ALTER TABLE projection_dlq
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        """
    )
    await pool.execute(
        """
        UPDATE projection_dlq
        SET dedupe_key = encode(digest(id::text, 'sha256'), 'hex')
        WHERE dedupe_key IS NULL
        """
    )
    await pool.execute("ALTER TABLE projection_dlq ALTER COLUMN dedupe_key SET NOT NULL")
    await pool.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'projection_dlq_projection_version_positive'
              AND conrelid = 'projection_dlq'::regclass
          ) THEN
            ALTER TABLE projection_dlq
              ADD CONSTRAINT projection_dlq_projection_version_positive
              CHECK (projection_version >= 1);
          END IF;
        END $$
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS projection_dlq_open_dedupe_uidx
          ON projection_dlq (tenant_id, dedupe_key)
          WHERE resolved_at IS NULL
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS projection_dlq_retry_ready_idx
          ON projection_dlq (next_attempt_at, created_at)
          WHERE resolved_at IS NULL
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_processing_batches (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            acceptance_id UUID NOT NULL,
            group_ordinal INT NOT NULL,
            dedupe_key TEXT NOT NULL UNIQUE,
            requested_by TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            workflow_version INT NOT NULL,
            workflow_hash TEXT NOT NULL,
            workflow_snapshot JSONB NOT NULL,
            projection_name TEXT NOT NULL,
            projection_version INT NOT NULL,
            content_type TEXT NOT NULL,
            event_type TEXT,
            events JSONB NOT NULL,
            event_ids UUID[] NOT NULL,
            tenant_ids UUID[] NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN (
                    'queued', 'running', 'retry_scheduled', 'completed', 'failed'
                )),
            attempts INT NOT NULL DEFAULT 0,
            max_attempts INT NOT NULL DEFAULT 10,
            next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_attempt_at TIMESTAMPTZ,
            lease_owner UUID,
            lease_expires_at TIMESTAMPTZ,
            error_class TEXT,
            error TEXT,
            result_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            UNIQUE (acceptance_id, group_ordinal)
        )
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS ingest_processing_worker_idx
          ON ingest_processing_batches (
            next_attempt_at, created_at, acceptance_id, group_ordinal
          )
          WHERE status IN ('queued', 'retry_scheduled')
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS ingest_processing_event_ids_gin_idx
          ON ingest_processing_batches USING GIN (event_ids)
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
    # --- Domain security tables (sql/011; soft-migrate for local/dev) ---
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS threat_intelligence (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID REFERENCES tenants (id) ON DELETE CASCADE,
            is_platform BOOLEAN NOT NULL DEFAULT FALSE,
            source TEXT NOT NULL,
            ip_address INET,
            location TEXT,
            abuse_confidence_score INT NOT NULL DEFAULT 0,
            otx_pulses INT NOT NULL DEFAULT 0,
            is_malicious BOOLEAN NOT NULL DEFAULT FALSE,
            raw_payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
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
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS playbooks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            trigger_conditions JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
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
        CREATE TABLE IF NOT EXISTS export_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            format TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            source_kind TEXT NOT NULL DEFAULT 'stream_results',
            object_key TEXT,
            checksum_sha256 TEXT,
            error TEXT,
            created_by_actor_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS training_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'completed',
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            artifact_path TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS threat_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            score DOUBLE PRECISION NOT NULL DEFAULT 0,
            features JSONB NOT NULL DEFAULT '[]'::jsonb,
            summary TEXT NOT NULL DEFAULT '',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # sql/014 — M2M / subprocessor principals (opaque token or bound Auth user).
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
                'analytics:read',
                'ml:read',
                'exports:read', 'exports:write',
                'vulnerabilities:read', 'vulnerabilities:write',
                'integrations:write',
                'siem:read', 'siem:write',
                'cases:read', 'cases:write',
                'playbooks:read', 'playbooks:write', 'playbooks:execute',
                'threat-intel:read',
                'reports:read', 'reports:write'
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

    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_erase_receipts (
            tenant_id UUID PRIMARY KEY,
            requested_by TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            deleted_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
            erased_credential_prefix TEXT,
            erased_credential_hash TEXT,
            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        """
        ALTER TABLE tenant_erase_receipts
        ADD COLUMN IF NOT EXISTS erased_credential_prefix TEXT
        """
    )
    await pool.execute(
        """
        ALTER TABLE tenant_erase_receipts
        ADD COLUMN IF NOT EXISTS erased_credential_hash TEXT
        """
    )
    await pool.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'tenant_erase_receipts_credential_tombstone_shape'
              AND conrelid = 'tenant_erase_receipts'::regclass
          ) THEN
            ALTER TABLE tenant_erase_receipts
              ADD CONSTRAINT tenant_erase_receipts_credential_tombstone_shape
              CHECK (
                (erased_credential_prefix IS NULL AND erased_credential_hash IS NULL)
                OR (
                  erased_credential_prefix IS NOT NULL
                  AND erased_credential_hash IS NOT NULL
                  AND char_length(erased_credential_prefix) = 8
                  AND erased_credential_hash ~ '^[0-9a-f]{64}$'
                )
              );
          END IF;
        END $$
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS tenant_erase_receipts_credential_hash_uidx
          ON tenant_erase_receipts (erased_credential_hash)
          WHERE erased_credential_hash IS NOT NULL
        """
    )


def reset_secure_schema_cache(pool: asyncpg.Pool | None = None) -> None:
    """Invalidate cached schema success (test isolation and pool lifecycle)."""
    if pool is None:
        _SCHEMA_SUCCESS.clear()
        _SCHEMA_LOCKS.clear()
        return
    pool_id = id(pool)
    for key in [key for key in _SCHEMA_SUCCESS if key[0] == pool_id]:
        _SCHEMA_SUCCESS.pop(key, None)
    for key in [key for key in _SCHEMA_LOCKS if key[0] == pool_id]:
        _SCHEMA_LOCKS.pop(key, None)


async def _run_schema_once(
    pool: asyncpg.Pool,
    *,
    mode: str,
    operation: Any,
) -> None:
    key = (id(pool), mode, bool(settings.SOFT_MIGRATE_SCHEMA), bool(settings.REQUIRE_RLS))
    if _SCHEMA_SUCCESS.get(key) is pool:
        return

    lock_entry = _SCHEMA_LOCKS.get(key)
    if lock_entry is None or lock_entry[0] is not pool:
        lock_entry = (pool, asyncio.Lock())
        _SCHEMA_LOCKS[key] = lock_entry
    async with lock_entry[1]:
        if _SCHEMA_SUCCESS.get(key) is pool:
            return
        await operation(pool)
        _SCHEMA_SUCCESS[key] = pool


async def assert_secure_schema(pool: asyncpg.Pool) -> None:
    """Verify the production schema once per pool/configuration signature."""
    await _run_schema_once(pool, mode="assert", operation=_assert_secure_schema_uncached)


async def ensure_secure_schema(pool: asyncpg.Pool) -> None:
    """Apply local soft-DDL or assert production schema once per pool."""
    await _run_schema_once(pool, mode="ensure", operation=_ensure_secure_schema_uncached)


# --- Membership checks ---
async def user_role_in_tenant(pool: asyncpg.Pool, *, tenant_id: UUID, user_id: str) -> str | None:
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


def _service_has_scope(scopes: frozenset[str], required: frozenset[str]) -> bool:
    if "*" in scopes:
        return True
    return bool(scopes & required)


async def require_tenant_access(
    pool: asyncpg.Pool,
    *,
    principal: AuthUser,
    tenant_id: UUID,
    min_roles: frozenset[str] | None = None,
    required_scopes: frozenset[str] | None = None,
) -> str:
    """Authorize a human member or a tenant-bound service principal.

    Services cannot cross tenants — `principal.tenant_id` must equal `tenant_id`.
    """
    if principal.kind == PrincipalKind.ERASE_TOMBSTONE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="erased credential is valid only for its completed erase receipt",
        )
    if principal.kind == PrincipalKind.SERVICE:
        if not principal.tenant_id or principal.tenant_id != str(tenant_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="service principal is bound to a different tenant",
            )
        if required_scopes and not _service_has_scope(principal.scopes, required_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient service scope",
            )
        bind_principal_context(
            principal_kind=principal.kind.value,
            principal_id=principal.user_id,
            tenant_id=str(tenant_id),
        )
        return "service"

    role = await require_member(
        pool,
        tenant_id=tenant_id,
        user_id=principal.user_id,
        min_roles=min_roles,
    )
    bind_principal_context(
        principal_kind=principal.kind.value,
        principal_id=principal.user_id,
        tenant_id=str(tenant_id),
    )
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
