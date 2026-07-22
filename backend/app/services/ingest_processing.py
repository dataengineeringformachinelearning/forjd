"""Durable post-commit processing for canonical sealed ingest batches."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from app.core.auth import AuthUser
from app.core.config import settings
from app.core.ingest_limits import MAX_INGEST_BATCH_EVENTS
from app.core.worker_health import WorkerHealthRegistry
from app.pipelines.ingest import run_ingest_flow
from app.services import projections as proj_svc
from app.services import tenants as tenant_svc
from app.workflows.models import WorkflowDefinition

logger = logging.getLogger("forjd.ingest_processing")

INGEST_PROCESSING_LEASE_SECONDS = 300
INGEST_PROCESSING_WORKER_INTERVAL_SECONDS = 2.0
INGEST_PROCESSING_MAX_ATTEMPTS = 10

PoolProvider = Callable[[], asyncpg.Pool | None]

_REQUIRED_COLUMNS = frozenset(
    {
        "id",
        "acceptance_id",
        "group_ordinal",
        "dedupe_key",
        "requested_by",
        "workflow_id",
        "workflow_version",
        "workflow_hash",
        "workflow_snapshot",
        "projection_name",
        "projection_version",
        "content_type",
        "event_type",
        "events",
        "event_ids",
        "tenant_ids",
        "status",
        "attempts",
        "max_attempts",
        "next_attempt_at",
        "last_attempt_at",
        "lease_owner",
        "lease_expires_at",
        "error_class",
        "error",
        "result_summary",
        "created_at",
        "updated_at",
        "completed_at",
    }
)
_REQUIRED_INDEXES = frozenset(
    {
        "ingest_processing_worker_idx",
        "ingest_processing_event_ids_gin_idx",
    }
)
_REQUIRED_TRIGGERS = frozenset(
    {
        "ingest_processing_identity_immutable",
        "ingest_processing_tenant_integrity",
    }
)
_REQUIRED_CONSTRAINTS = frozenset(
    {
        "ingest_processing_status_check",
        "ingest_processing_attempt_bounds",
        "ingest_processing_version_bounds",
        "ingest_processing_hash_shapes",
        "ingest_processing_snapshot_shapes",
        "ingest_processing_lease_shape",
        "ingest_processing_completion_shape",
    }
)


async def ensure_ingest_processing_schema(pool: asyncpg.Pool) -> None:
    """Assert the durable worker contract in production.

    The generic tenant-schema check proves that the table exists with RLS. This
    feature-specific check also proves that recovery can safely claim and replay
    immutable processing receipts instead of letting a worker fail forever in
    the background after readiness has passed.
    """
    await tenant_svc.ensure_secure_schema(pool)
    if settings.SOFT_MIGRATE_SCHEMA:
        await pool.execute(
            """
            CREATE OR REPLACE FUNCTION public.enforce_ingest_processing_tenant_integrity()
            RETURNS TRIGGER LANGUAGE plpgsql AS $$
            BEGIN
              IF cardinality(NEW.tenant_ids) IS DISTINCT FROM 1 THEN
                RAISE EXCEPTION 'ingest processing batch must contain exactly one tenant';
              END IF;
              IF EXISTS (
                SELECT 1
                FROM jsonb_array_elements(NEW.events) AS event_value
                WHERE event_value->>'tenant_id'
                  IS DISTINCT FROM NEW.tenant_ids[1]::text
              ) THEN
                RAISE EXCEPTION 'ingest processing event tenant does not match batch tenant';
              END IF;
              RETURN NEW;
            END $$;
            DROP TRIGGER IF EXISTS ingest_processing_tenant_integrity
              ON public.ingest_processing_batches;
            CREATE TRIGGER ingest_processing_tenant_integrity
              BEFORE INSERT OR UPDATE ON public.ingest_processing_batches
              FOR EACH ROW EXECUTE FUNCTION public.enforce_ingest_processing_tenant_integrity()
            """
        )
        return

    rows = await pool.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'ingest_processing_batches'
        """
    )
    present = {str(row["column_name"]) for row in rows}
    missing = sorted(_REQUIRED_COLUMNS - present)
    index_rows = await pool.fetch(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'ingest_processing_batches'
          AND indexname = ANY($1::text[])
        """,
        sorted(_REQUIRED_INDEXES),
    )
    present_indexes = {str(row["indexname"]) for row in index_rows}
    missing_indexes = sorted(_REQUIRED_INDEXES - present_indexes)
    trigger_rows = await pool.fetch(
        """
        SELECT trigger.tgname
        FROM pg_trigger trigger
        JOIN pg_class relation ON relation.oid = trigger.tgrelid
        JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND relation.relname = 'ingest_processing_batches'
          AND trigger.tgname = ANY($1::text[])
          AND NOT trigger.tgisinternal
        """,
        sorted(_REQUIRED_TRIGGERS),
    )
    present_triggers = {str(row["tgname"]) for row in trigger_rows}
    missing_triggers = sorted(_REQUIRED_TRIGGERS - present_triggers)
    constraint_rows = await pool.fetch(
        """
        SELECT constraint_record.conname
        FROM pg_constraint constraint_record
        JOIN pg_class relation ON relation.oid = constraint_record.conrelid
        JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND relation.relname = 'ingest_processing_batches'
          AND constraint_record.conname = ANY($1::text[])
          AND constraint_record.convalidated
        """,
        sorted(_REQUIRED_CONSTRAINTS),
    )
    present_constraints = {str(row["conname"]) for row in constraint_rows}
    missing_constraints = sorted(_REQUIRED_CONSTRAINTS - present_constraints)
    if missing or missing_indexes or missing_triggers or missing_constraints:
        details = [
            *(f"column:{name}" for name in missing),
            *(f"index:{name}" for name in missing_indexes),
            *(f"trigger:{name}" for name in missing_triggers),
            *(f"constraint:{name}" for name in missing_constraints),
        ]
        raise RuntimeError(
            "durable ingest processing schema missing; apply backend/sql/024: " + ", ".join(details)
        )


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise RuntimeError("processing workflow snapshot is not an object")
    return dict(value)


def _json_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeError("processing event snapshot is not an object array")
    return [dict(item) for item in value]


def workflow_snapshot(workflow: WorkflowDefinition) -> dict[str, Any]:
    """Return the complete validated configuration used by this processing group."""
    return workflow.model_dump(mode="json")


def workflow_snapshot_hash(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dumps(snapshot).encode("utf-8")).hexdigest()


def _processing_dedupe_key(
    *,
    workflow_id: str,
    workflow_hash: str,
    content_type: str,
    event_type: str | None,
    event_ids: list[str],
) -> str:
    payload = {
        "workflow_id": workflow_id,
        "workflow_hash": workflow_hash,
        "content_type": content_type,
        "event_type": event_type or "",
        "event_ids": event_ids,
    }
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _safe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not 1 <= len(events) <= MAX_INGEST_BATCH_EVENTS:
        raise ValueError("processing group is outside the canonical ingest batch limit")
    safe: list[dict[str, Any]] = []
    for event in events:
        event_id = str(UUID(str(event["event_id"])))
        tenant_id = str(UUID(str(event["tenant_id"])))
        cipher_len = int(event.get("cipher_len") or 0)
        if cipher_len < 0:
            raise ValueError("processing cipher_len must be nonnegative")
        routing = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        safe.append(
            {
                "event_id": event_id,
                "tenant_id": tenant_id,
                "key_id": str(event.get("key_id") or "")[:256],
                "cipher_len": cipher_len,
                "content_type": str(event.get("content_type") or "application/forjd-event+v1")[
                    :128
                ],
                "event_type": str(event.get("event_type") or "")[:128],
                "workflow_id": str(event.get("workflow_id") or "")[:128],
                "created_at": event.get("created_at"),
                # Routing tags only — never ciphertext or free-form plaintext.
                "metadata": {
                    key: value
                    for key, value in routing.items()
                    if key
                    in {
                        "source",
                        "channel",
                        "region",
                        "env",
                        "environment",
                        "product",
                        "component",
                        "namespace",
                        "device_id",
                        "series_id",
                        "label",
                        "labels",
                        "tags",
                    }
                },
            }
        )
    return safe


async def register_processing_batch(
    conn: asyncpg.Connection,
    *,
    acceptance_id: UUID,
    group_ordinal: int,
    requested_by: str,
    workflow: WorkflowDefinition,
    content_type: str,
    event_type: str | None,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create a processing receipt inside the sealed-event acceptance transaction."""
    safe_events = _safe_events(events)
    snapshot = workflow_snapshot(workflow)
    snapshot_hash = workflow_snapshot_hash(snapshot)
    event_ids = [event["event_id"] for event in safe_events]
    tenant_ids = sorted({event["tenant_id"] for event in safe_events})
    if len(tenant_ids) != 1:
        raise ValueError("each durable processing receipt must contain exactly one tenant")
    projection = workflow.pipeline.projection
    projection_version = projection.version if projection is not None else 1
    row = await conn.fetchrow(
        """
        INSERT INTO ingest_processing_batches (
            acceptance_id, group_ordinal, dedupe_key, requested_by,
            workflow_id, workflow_version, workflow_hash, workflow_snapshot,
            projection_name, projection_version, content_type, event_type,
            events, event_ids, tenant_ids, max_attempts
        )
        VALUES (
            $1::uuid, $2, $3, $4,
            $5, $6, $7, $8::jsonb,
            $9, $10, $11, $12,
            $13::jsonb, $14::uuid[], $15::uuid[], $16
        )
        ON CONFLICT (dedupe_key) DO UPDATE SET updated_at = NOW()
        RETURNING id::text, acceptance_id::text, group_ordinal, status,
                  attempts, max_attempts
        """,
        str(acceptance_id),
        group_ordinal,
        _processing_dedupe_key(
            workflow_id=workflow.id,
            workflow_hash=snapshot_hash,
            content_type=content_type,
            event_type=event_type,
            event_ids=event_ids,
        ),
        requested_by[:256],
        workflow.id,
        workflow.version,
        snapshot_hash,
        _json_dumps(snapshot),
        workflow.pipeline.projection_name,
        projection_version,
        content_type[:128],
        event_type[:128] if event_type else None,
        _json_dumps(safe_events),
        event_ids,
        tenant_ids,
        INGEST_PROCESSING_MAX_ATTEMPTS,
    )
    return dict(row)


async def find_processing_batches_covered_by_retry(
    pool: asyncpg.Pool | asyncpg.Connection,
    *,
    workflow_id: str,
    event_ids: list[str],
) -> list[dict[str, Any]]:
    """Find original stored groups fully covered by an all-duplicate retry.

    This also heals an original request that mixed already-known events with a
    new subgroup: the durable subgroup remains exact and ordered, while the
    retry proves it contains every event needed to resume that subgroup.
    """
    if not event_ids:
        return []
    rows = await pool.fetch(
        """
        SELECT id::text, acceptance_id::text, group_ordinal, status,
               attempts, max_attempts
        FROM ingest_processing_batches
        WHERE workflow_id = $1 AND event_ids <@ $2::uuid[]
        ORDER BY created_at, acceptance_id, group_ordinal, id
        """,
        workflow_id,
        event_ids,
    )
    return [dict(row) for row in rows]


async def wake_processing_batches(
    pool: asyncpg.Pool,
    *,
    batch_ids: list[str],
    revive_failed: bool,
) -> None:
    """Expedite pending work; an exact client retry may revive terminal failure."""
    if not batch_ids:
        return
    await pool.execute(
        """
        UPDATE ingest_processing_batches
        SET status = CASE
              WHEN status = 'failed' AND $2 THEN 'queued'
              ELSE status
            END,
            attempts = CASE WHEN status = 'failed' AND $2 THEN 0 ELSE attempts END,
            next_attempt_at = CASE
              WHEN status IN ('queued', 'retry_scheduled')
                   OR (status = 'failed' AND $2)
                THEN NOW()
              ELSE next_attempt_at
            END,
            error_class = CASE WHEN status = 'failed' AND $2 THEN NULL ELSE error_class END,
            error = CASE WHEN status = 'failed' AND $2 THEN NULL ELSE error END,
            updated_at = NOW()
        WHERE id = ANY($1::uuid[])
          AND status IN ('queued', 'retry_scheduled', 'failed')
        """,
        batch_ids,
        revive_failed,
    )


async def _recover_expired_processing_leases(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        UPDATE ingest_processing_batches
        SET status = CASE
              WHEN attempts >= max_attempts THEN 'failed'
              ELSE 'retry_scheduled'
            END,
            next_attempt_at = NOW(), lease_owner = NULL, lease_expires_at = NULL,
            error_class = COALESCE(error_class, 'WorkerLeaseExpired'),
            error = COALESCE(error, 'processing worker lease expired'),
            updated_at = NOW()
        WHERE status = 'running' AND lease_expires_at <= NOW()
        """
    )


async def _claim_processing_batches(
    pool: asyncpg.Pool,
    *,
    worker_id: UUID,
    batch_size: int,
    batch_ids: list[str] | None,
) -> list[asyncpg.Record]:
    limit = max(1, min(int(batch_size), 100))
    return await pool.fetch(
        """
        WITH candidates AS MATERIALIZED (
          SELECT id
          FROM ingest_processing_batches
          WHERE status IN ('queued', 'retry_scheduled')
            AND attempts < max_attempts
            AND next_attempt_at <= NOW()
            AND (lease_expires_at IS NULL OR lease_expires_at <= NOW())
            AND ($3::uuid[] IS NULL OR id = ANY($3::uuid[]))
          ORDER BY created_at, acceptance_id, group_ordinal, id
          FOR UPDATE SKIP LOCKED
          LIMIT $2
        )
        UPDATE ingest_processing_batches AS batch
        SET status = 'running', attempts = batch.attempts + 1,
            last_attempt_at = NOW(), lease_owner = $1::uuid,
            lease_expires_at = NOW() + ($4 * INTERVAL '1 second'),
            error_class = NULL, error = NULL, updated_at = NOW()
        FROM candidates
        WHERE batch.id = candidates.id
        RETURNING batch.*
        """,
        str(worker_id),
        limit,
        batch_ids if batch_ids is not None else None,
        INGEST_PROCESSING_LEASE_SECONDS,
    )


async def _heartbeat_processing_lease(
    pool: asyncpg.Pool,
    *,
    row: Any,
    worker_id: UUID,
    stop_event: asyncio.Event,
    lease_lost: asyncio.Event,
    health: WorkerHealthRegistry | None = None,
) -> None:
    """Extend one active receipt lease and mark any failed fence as lost."""
    interval = max(1.0, min(60.0, INGEST_PROCESSING_LEASE_SECONDS / 3))
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            return
        except TimeoutError:
            pass
        try:
            updated = await pool.execute(
                """
                UPDATE ingest_processing_batches
                SET lease_expires_at = NOW() + ($4 * INTERVAL '1 second'),
                    updated_at = NOW()
                WHERE id = $1::uuid AND status = 'running'
                  AND lease_owner = $2::uuid AND attempts = $3
                """,
                str(row["id"]),
                str(worker_id),
                int(row["attempts"]),
                INGEST_PROCESSING_LEASE_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - losing the fence must fail closed
            logger.warning(
                "ingest processing lease heartbeat failed batch=%s error_type=%s",
                row["id"],
                type(exc).__name__,
            )
            lease_lost.set()
            return
        if not str(updated).endswith(" 1"):
            logger.warning("ingest processing lease lost batch=%s", row["id"])
            lease_lost.set()
            return
        if health is not None:
            health.succeeded("ingest-processing")


def _validated_claim(row: Any) -> tuple[WorkflowDefinition, list[dict[str, Any]]]:
    snapshot = _json_object(row["workflow_snapshot"])
    expected_hash = str(row["workflow_hash"])
    actual_hash = workflow_snapshot_hash(snapshot)
    if not hmac.compare_digest(expected_hash, actual_hash):
        raise RuntimeError("stored workflow snapshot hash mismatch")
    workflow = WorkflowDefinition.model_validate(snapshot)
    projection = workflow.pipeline.projection
    projection_version = projection.version if projection is not None else 1
    if (
        workflow.id != str(row["workflow_id"])
        or workflow.version != int(row["workflow_version"])
        or workflow.pipeline.projection_name != str(row["projection_name"])
        or projection_version != int(row["projection_version"])
    ):
        raise RuntimeError("stored workflow snapshot contract mismatch")

    events = _json_list(row["events"])
    stored_event_ids = [str(value) for value in row["event_ids"]]
    stored_tenants = {str(value) for value in row["tenant_ids"]}
    if len(stored_tenants) != 1:
        raise RuntimeError("stored processing receipt must contain exactly one tenant")
    if [str(event.get("event_id")) for event in events] != stored_event_ids:
        raise RuntimeError("stored processing event order mismatch")
    if {str(event.get("tenant_id")) for event in events} != stored_tenants:
        raise RuntimeError("stored processing tenant set mismatch")
    return workflow, events


def _failure_delay_seconds(attempts: int) -> int:
    return min(3600, 30 * (2 ** max(0, min(attempts - 1, 7))))


async def _persist_processing_failure(
    pool: asyncpg.Pool,
    *,
    row: Any,
    worker_id: UUID,
    events: list[dict[str, Any]],
    exc: Exception,
) -> dict[str, Any]:
    attempts = int(row["attempts"])
    max_attempts = int(row["max_attempts"])
    terminal = attempts >= max_attempts
    async with pool.acquire() as conn, conn.transaction():
        for event in events:
            await proj_svc.enqueue_projection_dlq(
                conn,
                tenant_id=str(event["tenant_id"]),
                source_event_id=str(event["event_id"]),
                workflow_id=str(row["workflow_id"]),
                projection_name=str(row["projection_name"]),
                projection_version=int(row["projection_version"]),
                error=str(exc),
                error_class=type(exc).__name__,
                payload_meta=event,
            )
        status = await conn.execute(
            """
            UPDATE ingest_processing_batches
            SET status = CASE WHEN attempts >= max_attempts
                              THEN 'failed' ELSE 'retry_scheduled' END,
                next_attempt_at = NOW() + ($4 * INTERVAL '1 second'),
                lease_owner = NULL, lease_expires_at = NULL,
                error_class = $5, error = $6, updated_at = NOW()
            WHERE id = $1::uuid AND status = 'running' AND lease_owner = $2::uuid
              AND attempts = $3
            """,
            str(row["id"]),
            str(worker_id),
            attempts,
            _failure_delay_seconds(attempts),
            type(exc).__name__[:128],
            str(exc)[:2000],
        )
        if str(status) != "UPDATE 1":
            raise RuntimeError("ingest processing lease was lost while recording failure")
    return {
        "id": str(row["id"]),
        "ok": False,
        "status": "failed" if terminal else "retry_scheduled",
        "written": 0,
        "dlq_enqueued": len(events),
        "error": str(exc),
    }


async def _process_claimed_batch(
    pool: asyncpg.Pool,
    *,
    row: Any,
    worker_id: UUID,
    health: WorkerHealthRegistry | None = None,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    heartbeat_stop: asyncio.Event | None = None
    heartbeat_task: asyncio.Task[None] | None = None
    try:
        workflow, events = _validated_claim(row)
        event_ids = [str(event["event_id"]) for event in events]
        tenant_ids = sorted({str(event["tenant_id"]) for event in events})
        heartbeat_stop = asyncio.Event()
        lease_lost = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _heartbeat_processing_lease(
                pool,
                row=row,
                worker_id=worker_id,
                stop_event=heartbeat_stop,
                lease_lost=lease_lost,
                health=health,
            ),
            name=f"forjd-ingest-heartbeat-{row['id']}",
        )
        run = await asyncio.to_thread(
            run_ingest_flow,
            user_id=str(row["requested_by"]),
            tenant_ids=tenant_ids,
            accepted=len(events),
            event_ids=event_ids,
            events=events,
            content_type=str(row["content_type"]),
            event_type=str(row["event_type"]) if row["event_type"] else None,
            workflow_id=str(row["workflow_id"]),
            workflow_snapshot=workflow_snapshot(workflow),
        )
        if lease_lost.is_set():
            raise RuntimeError("ingest processing lease was lost during workflow execution")
        pathway = run.get("pathway") or {}
        if not pathway.get("ok"):
            raise RuntimeError(
                str(pathway.get("error") or "processor reported an unsuccessful result")
            )
        aggregate_ids = {
            tenant_id: [
                str(event["event_id"]) for event in events if str(event["tenant_id"]) == tenant_id
            ]
            for tenant_id in tenant_ids
        }
        summary = {
            "count": int(pathway.get("count") or 0),
            "anomaly_count": int(pathway.get("anomaly_count") or 0),
            "engine": str(pathway.get("engine") or ""),
        }
        async with pool.acquire() as conn, conn.transaction():
            written = await proj_svc.upsert_stream_results(
                conn,
                run.get("stream_results") or [],
                projection_version=int(row["projection_version"]),
                aggregate_event_ids_by_tenant=aggregate_ids,
                expected_tenant_ids=set(tenant_ids),
                expected_event_ids=set(event_ids),
            )
            for tenant_id, source_ids in aggregate_ids.items():
                await proj_svc.resolve_projection_dlq_for_events(
                    conn,
                    tenant_id=tenant_id,
                    source_event_ids=source_ids,
                    workflow_id=str(row["workflow_id"]),
                    projection_name=str(row["projection_name"]),
                    projection_version=int(row["projection_version"]),
                )
            # Durable live processing is the authoritative projection path.
            # Advance the matching stored-snapshot cursor in the same
            # transaction so the catch-up worker does not execute these events
            # again under a newer workflow configuration.
            await proj_svc.advance_checkpoint_from_meta(
                conn,
                meta_rows=events,
                workflow_id=str(row["workflow_id"]),
                projection_name=str(row["projection_name"]),
            )
            completed = await conn.execute(
                """
                UPDATE ingest_processing_batches
                SET status = 'completed', result_summary = $4::jsonb,
                    completed_at = NOW(), lease_owner = NULL, lease_expires_at = NULL,
                    error_class = NULL, error = NULL, updated_at = NOW()
                WHERE id = $1::uuid AND status = 'running'
                  AND lease_owner = $2::uuid AND attempts = $3
                """,
                str(row["id"]),
                str(worker_id),
                int(row["attempts"]),
                _json_dumps({**summary, "written": written}),
            )
            if str(completed) != "UPDATE 1":
                raise RuntimeError("ingest processing lease was lost before completion")
        return {
            "id": str(row["id"]),
            "ok": True,
            "status": "completed",
            "written": written,
            "dlq_enqueued": 0,
            "pathway": pathway,
            "prefect": {
                key: value for key, value in run.items() if key not in {"pathway", "stream_results"}
            },
        }
    except Exception as exc:  # noqa: BLE001 - durable processing boundary
        logger.exception("durable ingest processing failed batch=%s", row["id"])
        return await _persist_processing_failure(
            pool,
            row=row,
            worker_id=worker_id,
            events=events or _json_list(row["events"]),
            exc=exc,
        )
    finally:
        if heartbeat_stop is not None:
            heartbeat_stop.set()
        if heartbeat_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task


async def tick_ingest_processing(
    pool: asyncpg.Pool,
    *,
    batch_size: int = 10,
    worker_id: UUID | None = None,
    batch_ids: list[str] | None = None,
    _schema_ready: bool = False,
    health: WorkerHealthRegistry | None = None,
) -> list[dict[str, Any]]:
    """Claim and independently process due receipts; safe across API replicas."""
    if not _schema_ready:
        await ensure_ingest_processing_schema(pool)
    if batch_ids is not None and not batch_ids:
        return []
    owner = worker_id or uuid4()
    await _recover_expired_processing_leases(pool)
    claim_limit = max(1, min(int(batch_size), 100))
    remaining_ids = list(dict.fromkeys(batch_ids)) if batch_ids is not None else None
    outcomes: list[dict[str, Any]] = []
    for _ in range(claim_limit):
        if remaining_ids is not None and not remaining_ids:
            break
        rows = await _claim_processing_batches(
            pool,
            worker_id=owner,
            batch_size=1,
            batch_ids=remaining_ids,
        )
        if not rows:
            break
        row = rows[0]
        if remaining_ids is not None:
            claimed_id = str(row["id"])
            remaining_ids = [value for value in remaining_ids if str(value) != claimed_id]
        try:
            outcomes.append(
                await _process_claimed_batch(pool, row=row, worker_id=owner, health=health)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - one lease cannot block later rows
            logger.exception(
                "ingest processing persistence failed batch=%s error_type=%s",
                row["id"],
                type(exc).__name__,
            )
            outcomes.append(
                {
                    "id": str(row["id"]),
                    "ok": False,
                    "status": "running",
                    "written": 0,
                    "dlq_enqueued": 0,
                    "error": "processing persistence failed; lease recovery will retry",
                }
            )
    return outcomes


async def fetch_processing_batch_states(
    pool: asyncpg.Pool,
    *,
    batch_ids: list[str],
) -> list[dict[str, Any]]:
    if not batch_ids:
        return []
    rows = await pool.fetch(
        """
        SELECT id::text, acceptance_id::text, group_ordinal, workflow_id,
               status, attempts, max_attempts, next_attempt_at, error_class,
               result_summary
        FROM ingest_processing_batches
        WHERE id = ANY($1::uuid[])
        ORDER BY created_at, acceptance_id, group_ordinal, id
        """,
        batch_ids,
    )
    return [dict(row) for row in rows]


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


async def get_processing_batch_status(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    batch_id: UUID,
) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        SELECT id::text, acceptance_id::text, group_ordinal, workflow_id,
               workflow_version, workflow_hash, projection_name, projection_version,
               tenant_ids, cardinality(event_ids) AS event_count, status,
               attempts, max_attempts, next_attempt_at, last_attempt_at,
               error_class, result_summary, created_at, updated_at, completed_at
        FROM ingest_processing_batches
        WHERE id = $1::uuid
        """,
        str(batch_id),
    )
    if row is None:
        raise LookupError("ingest processing batch not found")
    tenant_ids = [UUID(str(value)) for value in row["tenant_ids"]]
    for tenant_id in tenant_ids:
        await tenant_svc.require_tenant_access(
            pool,
            principal=user,
            tenant_id=tenant_id,
            min_roles=frozenset({"owner", "admin", "member"}),
            required_scopes=frozenset({"ingest:read"}),
        )
    summary = row["result_summary"] or {}
    if isinstance(summary, str):
        summary = json.loads(summary)
    return {
        "id": row["id"],
        "acceptance_id": row["acceptance_id"],
        "group_ordinal": row["group_ordinal"],
        "workflow_id": row["workflow_id"],
        "workflow_version": row["workflow_version"],
        "workflow_hash": row["workflow_hash"],
        "projection_name": row["projection_name"],
        "projection_version": row["projection_version"],
        "tenant_ids": [str(value) for value in tenant_ids],
        "event_count": row["event_count"],
        "status": row["status"],
        "attempts": row["attempts"],
        "max_attempts": row["max_attempts"],
        "next_attempt_at": _iso(row["next_attempt_at"]),
        "last_attempt_at": _iso(row["last_attempt_at"]),
        "error_class": row["error_class"],
        "result_summary": dict(summary),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
        "completed_at": _iso(row["completed_at"]),
    }


async def run_ingest_processing_worker(
    pool_provider: PoolProvider,
    stop_event: asyncio.Event,
    *,
    interval_seconds: float = INGEST_PROCESSING_WORKER_INTERVAL_SECONDS,
    batch_size: int = 10,
    health: WorkerHealthRegistry | None = None,
) -> None:
    """Supervised worker that also tolerates a database becoming ready lazily.

    Lifespan integration should start this task even when the initial pool is
    ``None`` and pass a provider reading the current ``app.state.db_pool``.
    """
    owner = uuid4()
    interval = max(0.25, min(float(interval_seconds), 60.0))
    schema_pool: asyncpg.Pool | None = None
    logger.info("ingest processing worker started owner=%s", owner)
    while not stop_event.is_set():
        processed = 0
        try:
            pool = pool_provider()
            if pool is not None:
                if pool is not schema_pool:
                    await ensure_ingest_processing_schema(pool)
                    schema_pool = pool
                outcomes = await tick_ingest_processing(
                    pool,
                    batch_size=batch_size,
                    worker_id=owner,
                    _schema_ready=True,
                    health=health,
                )
                processed = len(outcomes)
                if health is not None:
                    if any(
                        not outcome.get("ok") and outcome.get("status") == "running"
                        for outcome in outcomes
                    ):
                        health.failed(
                            "ingest-processing",
                            RuntimeError("processing failure could not be persisted"),
                        )
                    else:
                        health.succeeded("ingest-processing")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - supervised retry loop
            schema_pool = None
            if health is not None:
                health.failed("ingest-processing", exc)
            logger.warning(
                "ingest processing worker tick failed error_type=%s",
                type(exc).__name__,
            )
        delay = 0.05 if processed else interval
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
    logger.info("ingest processing worker stopped owner=%s", owner)
