"""PII-minimized normalized security-signal lane for headless SIEM/SOAR."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder

from app.core.auth import AuthUser
from app.core.config import settings
from app.models.siem import CreateSecuritySignalRequest
from app.services import audit
from app.services import playbooks as playbook_svc
from app.services import soc as soc_svc
from app.services import tenants as tenant_svc
from app.services.correlation import evaluate_correlation_rules

_REQUIRED_REPLAY_COLUMNS = frozenset(
    {
        ("security_signals", "processing_status"),
        ("security_signals", "processing_result"),
        ("security_signals", "processing_completed_at"),
        ("correlation_receipts", "result_snapshot"),
    }
)
_REQUIRED_REPLAY_INDEXES = frozenset(
    {
        "security_signals_processing_idx",
        "playbook_runs_continuation_ready_idx",
    }
)
_REQUIRED_REPLAY_CONSTRAINTS = frozenset(
    {
        "security_signals_processing_contract",
        "correlation_receipts_result_snapshot_object",
    }
)


async def ensure_siem_schema(pool: asyncpg.Pool) -> None:
    """Create the development shape or assert the SQL/025 replay contract."""
    await tenant_svc.ensure_secure_schema(pool)
    if not settings.SOFT_MIGRATE_SCHEMA:
        secure_rows = await pool.fetch(
            """
            SELECT relation.relname
            FROM pg_class relation
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
              AND relation.relname = ANY($1::text[])
              AND relation.relrowsecurity = TRUE
            """,
            ["security_signals", "correlation_receipts"],
        )
        present_secure = {str(row["relname"]) for row in secure_rows}
        missing_secure = sorted({"security_signals", "correlation_receipts"} - present_secure)
        column_rows = await pool.fetch(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ANY($1::text[])
            """,
            ["security_signals", "correlation_receipts"],
        )
        present_columns = {(str(row["table_name"]), str(row["column_name"])) for row in column_rows}
        missing_columns = sorted(_REQUIRED_REPLAY_COLUMNS - present_columns)
        index_rows = await pool.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = ANY($1::text[])
            """,
            sorted(_REQUIRED_REPLAY_INDEXES),
        )
        present_indexes = {str(row["indexname"]) for row in index_rows}
        missing_indexes = sorted(_REQUIRED_REPLAY_INDEXES - present_indexes)
        constraint_rows = await pool.fetch(
            """
            SELECT constraint_record.conname
            FROM pg_constraint constraint_record
            JOIN pg_class relation ON relation.oid = constraint_record.conrelid
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
              AND relation.relname = ANY($1::text[])
              AND constraint_record.conname = ANY($2::text[])
              AND constraint_record.convalidated
            """,
            ["security_signals", "correlation_receipts"],
            sorted(_REQUIRED_REPLAY_CONSTRAINTS),
        )
        present_constraints = {str(row["conname"]) for row in constraint_rows}
        missing_constraints = sorted(_REQUIRED_REPLAY_CONSTRAINTS - present_constraints)
        if missing_secure or missing_columns or missing_indexes or missing_constraints:
            details = [
                *(f"rls:{name}" for name in missing_secure),
                *(f"column:{table}.{column}" for table, column in missing_columns),
                *(f"index:{name}" for name in missing_indexes),
                *(f"constraint:{name}" for name in missing_constraints),
            ]
            raise RuntimeError(
                "secure SIEM replay schema missing; apply backend/sql/025: " + ", ".join(details)
            )
        return
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS security_signals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            client_signal_id TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            observed_at TIMESTAMPTZ NOT NULL,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'medium',
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            confidence INT NOT NULL DEFAULT 50,
            observables JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            processing_status TEXT NOT NULL DEFAULT 'processing',
            processing_result JSONB NOT NULL DEFAULT '{}'::jsonb,
            processing_completed_at TIMESTAMPTZ,
            created_by_actor_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (char_length(client_signal_id) BETWEEN 1 AND 128),
            CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
            CHECK (category IN (
                'authentication', 'malware', 'network', 'data_loss', 'vulnerability',
                'cloud', 'endpoint', 'application', 'threat_intelligence', 'other'
            )),
            CHECK (severity IN ('informational', 'low', 'medium', 'high', 'critical')),
            CHECK (confidence BETWEEN 0 AND 100),
            CHECK (jsonb_typeof(observables) = 'array' AND jsonb_array_length(observables) <= 32),
            CHECK (jsonb_typeof(metadata) = 'object'),
            CHECK (processing_status IN ('processing', 'completed')),
            CHECK (jsonb_typeof(processing_result) = 'object'),
            UNIQUE (tenant_id, client_signal_id)
        )
        """
    )
    for statement in (
        "ALTER TABLE security_signals ADD COLUMN IF NOT EXISTS processing_status "
        "TEXT NOT NULL DEFAULT 'processing'",
        "ALTER TABLE security_signals ADD COLUMN IF NOT EXISTS processing_result "
        "JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE security_signals ADD COLUMN IF NOT EXISTS processing_completed_at TIMESTAMPTZ",
    ):
        await pool.execute(statement)
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS security_signals_tenant_observed_idx
        ON security_signals (tenant_id, observed_at DESC, id DESC)
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS security_signals_tenant_severity_idx
        ON security_signals (tenant_id, severity, observed_at DESC)
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS security_signals_processing_idx
        ON security_signals (created_at, id)
        WHERE processing_status = 'processing'
        """
    )


def _content_sha256(signal: CreateSecuritySignalRequest) -> str:
    content = signal.model_dump(
        mode="json",
        exclude={"correlate", "run_playbooks"},
    )
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def create_signal(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    signal: CreateSecuritySignalRequest,
) -> dict[str, Any]:
    tenant_id = signal.tenant_id
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"siem:write"}),
    )
    # Scope checks happen before insertion so a partially authorized caller can
    # never create a signal and then fail halfway through requested automation.
    if signal.correlate:
        await tenant_svc.require_tenant_access(
            pool,
            principal=user,
            tenant_id=tenant_id,
            min_roles=frozenset({"owner", "admin", "member"}),
            required_scopes=frozenset({"cases:write"}),
        )
    if signal.run_playbooks:
        await tenant_svc.require_tenant_access(
            pool,
            principal=user,
            tenant_id=tenant_id,
            min_roles=frozenset({"owner", "admin", "member"}),
            required_scopes=frozenset({"playbooks:execute"}),
        )
    await ensure_siem_schema(pool)
    digest = _content_sha256(signal)
    await audit.record_required(
        pool,
        action="siem.signal.accept_attempt",
        actor_user_id=user.actor_id,
        tenant_id=tenant_id,
        resource_type="security_signal",
        resource_id=signal.client_signal_id,
        details={
            "source": signal.source,
            "category": signal.category,
            "severity": signal.severity,
        },
    )
    row = await pool.fetchrow(
        """
        INSERT INTO security_signals (
            tenant_id, client_signal_id, content_sha256, observed_at, source,
            category, signal_type, severity, title, summary, confidence,
            observables, metadata, created_by_actor_id
        )
        VALUES (
            $1::uuid, $2, $3, $4, $5,
            $6, $7, $8, $9, $10, $11,
            $12::jsonb, $13::jsonb, $14::uuid
        )
        ON CONFLICT (tenant_id, client_signal_id) DO NOTHING
        RETURNING id::text, tenant_id::text, client_signal_id, content_sha256,
                  observed_at, source, category, signal_type, severity, title,
                  summary, confidence, observables, metadata,
                  processing_status, processing_result, processing_completed_at,
                  created_by_actor_id::text, created_at
        """,
        str(tenant_id),
        signal.client_signal_id,
        digest,
        signal.observed_at,
        signal.source,
        signal.category,
        signal.signal_type,
        signal.severity,
        signal.title,
        signal.summary,
        signal.confidence,
        json.dumps([item.model_dump(mode="json") for item in signal.observables]),
        json.dumps(signal.metadata),
        user.user_id,
    )
    created = row is not None
    if row is None:
        row = await pool.fetchrow(
            """
            SELECT id::text, tenant_id::text, client_signal_id, content_sha256,
                   observed_at, source, category, signal_type, severity, title,
                   summary, confidence, observables, metadata,
                   processing_status, processing_result, processing_completed_at,
                   created_by_actor_id::text, created_at
            FROM security_signals
            WHERE tenant_id = $1::uuid AND client_signal_id = $2
            """,
            str(tenant_id),
            signal.client_signal_id,
        )
        if row is None:
            raise RuntimeError("idempotent security signal could not be resolved")
        if row["content_sha256"] != digest:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="client_signal_id was already used with different normalized content",
            )
    item = _signal_dict(row)
    if not created and row.get("processing_status") == "completed":
        snapshot = _signal_processing_result(row.get("processing_result"))
        await _authorize_signal_snapshot(
            pool,
            user=user,
            tenant_id=tenant_id,
            snapshot=snapshot,
        )
        return {"signal": item, "duplicate": True, **snapshot}
    if created:
        await audit.record_required(
            pool,
            action="siem.signal.create",
            actor_user_id=user.actor_id,
            tenant_id=tenant_id,
            resource_type="security_signal",
            resource_id=item["id"],
            details={
                "client_signal_id": signal.client_signal_id,
                "source": signal.source,
                "category": signal.category,
                "severity": signal.severity,
                "observable_count": len(signal.observables),
            },
        )
    # A processing retry heals a crash after signal persistence. Once the
    # receipt is completed, the branch above returns the immutable result and
    # never evaluates today's rules or playbooks for yesterday's request.
    context = _correlation_context(signal)
    matches = evaluate_correlation_rules(context)
    case = None
    signal_id = UUID(item["id"])
    if signal.correlate and matches:
        case = await soc_svc.open_case_from_context(
            pool,
            user=user,
            tenant_id=tenant_id,
            context=context,
            source_signal_id=signal_id,
        )
    playbook_runs: list[dict[str, Any]] = []
    if signal.run_playbooks:
        playbook_runs = await playbook_svc.run_matching_playbooks(
            pool,
            user=user,
            tenant_id=tenant_id,
            context=context,
            idempotency_prefix=f"signal:{signal_id}",
            trigger_source="security_signal",
            source_signal_id=signal_id,
        )
    snapshot = jsonable_encoder(
        {
            "matches": [
                {
                    "rule_id": match.rule_id,
                    "title": match.title,
                    "severity": match.severity,
                    "description": match.description,
                }
                for match in matches
            ],
            "case": case,
            "playbook_runs": playbook_runs,
        }
    )
    completed = await pool.fetchrow(
        """
        WITH updated AS (
          UPDATE security_signals
          SET processing_status = 'completed', processing_result = $3::jsonb,
              processing_completed_at = COALESCE(processing_completed_at, NOW())
          WHERE id = $1::uuid AND tenant_id = $2::uuid
            AND processing_status = 'processing'
          RETURNING id::text
        ), audit_receipt AS (
          INSERT INTO audit_events (
            actor_user_id, tenant_id, action, resource_type, resource_id, details
          )
          SELECT $4, $2::uuid, $5, 'security_signal', updated.id, $6::jsonb
          FROM updated
          RETURNING id
        )
        SELECT updated.id
        FROM updated CROSS JOIN audit_receipt
        """,
        item["id"],
        str(tenant_id),
        json.dumps(snapshot),
        user.actor_id,
        "siem.signal.process" if created else "siem.signal.retry",
        json.dumps(
            {
                "match_count": len(matches),
                "case_created": case is not None,
                "playbook_run_count": len(playbook_runs),
                "duplicate": not created,
            }
        ),
    )
    if completed is None:
        completed_row = await pool.fetchrow(
            """
            SELECT processing_status, processing_result
            FROM security_signals
            WHERE id = $1::uuid AND tenant_id = $2::uuid
            """,
            item["id"],
            str(tenant_id),
        )
        if completed_row is None or completed_row["processing_status"] != "completed":
            raise RuntimeError("security signal processing receipt could not be completed")
        snapshot = _signal_processing_result(completed_row["processing_result"])
    return {"signal": item, "duplicate": not created, **snapshot}


async def list_signals(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    severity: str | None = None,
    category: str | None = None,
    source: str | None = None,
    observed_after: datetime | None = None,
    observed_before: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"siem:read"}),
    )
    await ensure_siem_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, client_signal_id, content_sha256,
               observed_at, source, category, signal_type, severity, title,
               summary, confidence, observables, metadata,
               created_by_actor_id::text, created_at
        FROM security_signals
        WHERE tenant_id = $1::uuid
          AND ($2::text IS NULL OR severity = $2)
          AND ($3::text IS NULL OR category = $3)
          AND ($4::text IS NULL OR source = $4)
          AND ($5::timestamptz IS NULL OR observed_at >= $5)
          AND ($6::timestamptz IS NULL OR observed_at <= $6)
        ORDER BY observed_at DESC, id DESC
        LIMIT $7
        """,
        str(tenant_id),
        severity,
        category,
        source,
        observed_after,
        observed_before,
        max(1, min(limit, 500)),
    )
    return [_signal_dict(row) for row in rows]


async def _authorize_signal_snapshot(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    snapshot: dict[str, Any],
) -> None:
    """Authorize replayed automation results independently of request flags."""
    if snapshot["case"] is not None:
        await tenant_svc.require_tenant_access(
            pool,
            principal=user,
            tenant_id=tenant_id,
            min_roles=frozenset({"owner", "admin", "member"}),
            required_scopes=frozenset({"cases:write"}),
        )
    if snapshot["playbook_runs"]:
        await tenant_svc.require_tenant_access(
            pool,
            principal=user,
            tenant_id=tenant_id,
            min_roles=frozenset({"owner", "admin", "member"}),
            required_scopes=frozenset({"playbooks:execute"}),
        )


def _correlation_context(signal: CreateSecuritySignalRequest) -> dict[str, Any]:
    metadata = signal.metadata
    raw_abuse = metadata.get("abuse_confidence_score")
    abuse_score = (
        int(raw_abuse)
        if isinstance(raw_abuse, (int, float)) and not isinstance(raw_abuse, bool)
        else 0
    )
    raw_anomaly = metadata.get("anomaly_score")
    anomaly_score = (
        float(raw_anomaly)
        if isinstance(raw_anomaly, (int, float)) and not isinstance(raw_anomaly, bool)
        else 0.0
    )
    high_threat = signal.category in {"malware", "threat_intelligence"} and signal.severity in {
        "high",
        "critical",
    }
    return {
        "event_type": "security_signal",
        "signal_type": signal.signal_type,
        "category": signal.category,
        "severity": signal.severity,
        "source": signal.source,
        "confidence": signal.confidence,
        "is_malicious": metadata.get("is_malicious") is True or high_threat,
        "threat_match": metadata.get("threat_match") is True or high_threat,
        "abuse_confidence_score": abuse_score,
        "anomaly_score": anomaly_score,
        "behavioral_entropy": metadata.get("behavioral_entropy"),
        "behavioral": metadata.get("behavioral") or {},
        "has_ip_observable": any(item.type in {"ipv4", "ipv6"} for item in signal.observables),
    }


def _json_value(value: Any, *, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _signal_processing_result(value: Any) -> dict[str, Any]:
    parsed = _json_value(value, default={})
    if not isinstance(parsed, dict):
        parsed = {}
    matches = parsed.get("matches")
    case = parsed.get("case")
    playbook_runs = parsed.get("playbook_runs")
    return {
        "matches": [item for item in matches if isinstance(item, dict)]
        if isinstance(matches, list)
        else [],
        "case": case if isinstance(case, dict) else None,
        "playbook_runs": [item for item in playbook_runs if isinstance(item, dict)]
        if isinstance(playbook_runs, list)
        else [],
    }


def _signal_dict(row: asyncpg.Record) -> dict[str, Any]:
    observables = _json_value(row["observables"], default=[])
    metadata = _json_value(row["metadata"], default={})
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "client_signal_id": row["client_signal_id"],
        "observed_at": row["observed_at"],
        "source": row["source"],
        "category": row["category"],
        "signal_type": row["signal_type"],
        "severity": row["severity"],
        "title": row["title"],
        "summary": row["summary"],
        "confidence": int(row["confidence"]),
        "observables": observables if isinstance(observables, list) else [],
        "metadata": metadata if isinstance(metadata, dict) else {},
        "created_by_actor_id": row["created_by_actor_id"],
        "created_at": row["created_at"],
    }
