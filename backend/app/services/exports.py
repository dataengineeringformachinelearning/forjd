"""Durable, idempotent tenant exports backed by S3-compatible object storage."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

import asyncpg
import polars as pl
from fastapi import HTTPException, status

from app.core import object_storage
from app.core.auth import AuthUser
from app.core.config import settings
from app.core.worker_health import WorkerHealthRegistry
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.exports")

ExportFormat = Literal["csv", "json", "parquet", "pdf"]
_CONTENT_TYPES: dict[str, str] = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
    "parquet": "application/vnd.apache.parquet",
    "pdf": "application/pdf",
}
_EXPORT_LEASE_SECONDS = 300
_EXPORT_HEARTBEAT_SECONDS = 30
_SOURCE_PAGE_ROWS = 1_000


class ExportSourceTooLargeError(ValueError):
    """Raised before source materialization can exhaust a worker's memory."""


_REQUIRED_COLUMNS = frozenset(
    {
        "id",
        "tenant_id",
        "format",
        "status",
        "source_kind",
        "idempotency_key",
        "request_fingerprint",
        "filters",
        "object_key",
        "checksum_sha256",
        "byte_size",
        "content_type",
        "error",
        "attempts",
        "max_attempts",
        "next_attempt_at",
        "lease_owner",
        "lease_expires_at",
        "created_by_actor_id",
        "created_at",
        "completed_at",
        "expires_at",
    }
)
_REQUIRED_INDEXES = frozenset(
    {
        "export_jobs_tenant_idempotency_idx",
        "export_jobs_worker_idx",
        "export_jobs_expiry_idx",
        "export_jobs_artifact_cleanup_idx",
    }
)
_REQUIRED_CONSTRAINTS = frozenset(
    {
        "export_jobs_format_check",
        "export_jobs_status_check",
        "export_jobs_source_kind_check",
        "export_jobs_attempts_bounds",
        "export_jobs_artifact_metadata",
        "export_jobs_lease_shape",
    }
)


async def ensure_export_schema(pool: asyncpg.Pool) -> None:
    """Assert the production migration or create the complete local/dev shape."""
    await tenant_svc.ensure_secure_schema(pool)
    if not settings.SOFT_MIGRATE_SCHEMA:
        rows = await pool.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'export_jobs'
            """
        )
        present = {str(row["column_name"]) for row in rows}
        missing = sorted(_REQUIRED_COLUMNS - present)
        index_rows = await pool.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'export_jobs'
              AND indexname = ANY($1::text[])
            """,
            sorted(_REQUIRED_INDEXES),
        )
        present_indexes = {str(row["indexname"]) for row in index_rows}
        missing_indexes = sorted(_REQUIRED_INDEXES - present_indexes)
        constraint_rows = await pool.fetch(
            """
            SELECT constraint_record.conname
            FROM pg_constraint constraint_record
            JOIN pg_class relation ON relation.oid = constraint_record.conrelid
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
              AND relation.relname = 'export_jobs'
              AND constraint_record.conname = ANY($1::text[])
              AND constraint_record.convalidated
            """,
            sorted(_REQUIRED_CONSTRAINTS),
        )
        present_constraints = {str(row["conname"]) for row in constraint_rows}
        missing_constraints = sorted(_REQUIRED_CONSTRAINTS - present_constraints)
        if missing or missing_indexes or missing_constraints:
            details = [
                *(f"column:{name}" for name in missing),
                *(f"index:{name}" for name in missing_indexes),
                *(f"constraint:{name}" for name in missing_constraints),
            ]
            raise RuntimeError(
                "secure export schema missing; apply backend/sql/023: " + ", ".join(details)
            )
        return

    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS export_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            format TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            source_kind TEXT NOT NULL DEFAULT 'stream_results',
            idempotency_key TEXT,
            request_fingerprint TEXT,
            filters JSONB NOT NULL DEFAULT '{}'::jsonb,
            object_key TEXT,
            checksum_sha256 TEXT,
            byte_size BIGINT NOT NULL DEFAULT 0,
            content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            error TEXT,
            attempts INT NOT NULL DEFAULT 0,
            max_attempts INT NOT NULL DEFAULT 5,
            next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            lease_owner UUID,
            lease_expires_at TIMESTAMPTZ,
            created_by_actor_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ
        )
        """
    )
    additions = (
        "ADD COLUMN IF NOT EXISTS idempotency_key TEXT",
        "ADD COLUMN IF NOT EXISTS request_fingerprint TEXT",
        "ADD COLUMN IF NOT EXISTS filters JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ADD COLUMN IF NOT EXISTS byte_size BIGINT NOT NULL DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'application/octet-stream'",
        "ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0",
        (
            "ADD COLUMN IF NOT EXISTS max_attempts INT NOT NULL DEFAULT "
            f"{settings.EXPORT_MAX_ATTEMPTS}"
        ),
        "ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        "ADD COLUMN IF NOT EXISTS lease_owner UUID",
        "ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ",
        "ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ",
    )
    for addition in additions:
        await pool.execute(f"ALTER TABLE export_jobs {addition}")
    # Drop legacy SQL/011 checks before writing newer durable states.
    await pool.execute(
        """
        ALTER TABLE export_jobs DROP CONSTRAINT IF EXISTS export_jobs_status_check;
        ALTER TABLE export_jobs DROP CONSTRAINT IF EXISTS export_jobs_format_check;
        ALTER TABLE export_jobs DROP CONSTRAINT IF EXISTS export_jobs_source_kind_check;
        ALTER TABLE export_jobs DROP CONSTRAINT IF EXISTS export_jobs_attempts_bounds;
        ALTER TABLE export_jobs DROP CONSTRAINT IF EXISTS export_jobs_artifact_metadata;
        ALTER TABLE export_jobs DROP CONSTRAINT IF EXISTS export_jobs_lease_shape;
        """
    )
    await pool.execute(
        """
        UPDATE export_jobs
        SET idempotency_key = COALESCE(idempotency_key, 'legacy:' || id::text),
            request_fingerprint = COALESCE(
              request_fingerprint,
              encode(digest(format || ':' || source_kind, 'sha256'), 'hex')
            ),
            content_type = CASE format
              WHEN 'csv' THEN 'text/csv; charset=utf-8'
              WHEN 'json' THEN 'application/json'
              WHEN 'parquet' THEN 'application/vnd.apache.parquet'
              ELSE content_type
            END,
            status = CASE
              WHEN status = 'pending'
                OR (status = 'running' AND (
                  lease_owner IS NULL OR lease_expires_at IS NULL
                ))
              THEN 'queued'
              ELSE status
            END,
            lease_owner = CASE
              WHEN status = 'pending'
                OR (status = 'running' AND (
                  lease_owner IS NULL OR lease_expires_at IS NULL
                ))
              THEN NULL
              ELSE lease_owner
            END,
            lease_expires_at = CASE
              WHEN status = 'pending'
                OR (status = 'running' AND (
                  lease_owner IS NULL OR lease_expires_at IS NULL
                ))
              THEN NULL
              ELSE lease_expires_at
            END,
            next_attempt_at = CASE
              WHEN status = 'pending'
                OR (status = 'running' AND (
                  lease_owner IS NULL OR lease_expires_at IS NULL
                ))
              THEN NOW()
              ELSE next_attempt_at
            END
        """
    )
    await pool.execute(
        """
        UPDATE export_jobs
        SET filters = filters || jsonb_build_object('legacy_source_kind', source_kind),
            source_kind = 'stream_results', status = 'failed',
            error = COALESCE(error, 'LegacyUnsupportedSourceKind'),
            completed_at = COALESCE(completed_at, NOW())
        WHERE source_kind NOT IN (
          'stream_results', 'analytics', 'threat', 'lighthouse', 'vulnerabilities'
        )
        """
    )
    await pool.execute(
        """
        ALTER TABLE export_jobs ADD CONSTRAINT export_jobs_format_check
          CHECK (format IN ('csv', 'json', 'parquet', 'pdf'));
        ALTER TABLE export_jobs ADD CONSTRAINT export_jobs_status_check
          CHECK (status IN (
            'queued', 'running', 'retry_scheduled', 'completed', 'failed', 'expired'
          ));
        ALTER TABLE export_jobs ADD CONSTRAINT export_jobs_source_kind_check
          CHECK (source_kind IN (
            'stream_results', 'analytics', 'threat', 'lighthouse', 'vulnerabilities'
          ));
        ALTER TABLE export_jobs ADD CONSTRAINT export_jobs_lease_shape CHECK (
          (status = 'running' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
          OR (status <> 'running' AND lease_owner IS NULL AND lease_expires_at IS NULL)
        );
        """
    )
    await pool.execute(
        """
        ALTER TABLE export_jobs ALTER COLUMN idempotency_key SET NOT NULL;
        ALTER TABLE export_jobs ALTER COLUMN request_fingerprint SET NOT NULL;
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS export_jobs_tenant_idempotency_idx
        ON export_jobs (tenant_id, idempotency_key)
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS export_jobs_worker_idx
        ON export_jobs (next_attempt_at, created_at, id)
        WHERE status IN ('queued', 'retry_scheduled')
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS export_jobs_expiry_idx
        ON export_jobs (expires_at, id)
        WHERE status = 'completed' AND object_key IS NOT NULL
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS export_jobs_artifact_cleanup_idx
        ON export_jobs (next_attempt_at, id)
        WHERE status = 'failed' AND object_key IS NOT NULL
        """
    )


def _request_fingerprint(
    *, format: str, source_kind: str, limit: int, days: int, site_url: str | None
) -> str:
    canonical = json.dumps(
        {
            "format": format,
            "source_kind": source_kind,
            "limit": limit,
            "days": days,
            "site_url": site_url or "",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


async def create_export_job(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    idempotency_key: str,
    format: ExportFormat = "csv",
    source_kind: str = "stream_results",
    limit: int = 10_000,
    days: int = 7,
    site_url: str | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"exports:write"}),
    )
    await ensure_export_schema(pool)
    if settings.is_production and not object_storage.is_configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="durable export object storage is not configured",
        )
    bounded_limit = max(1, min(int(limit), 100_000))
    if format == "pdf" and bounded_limit > 1_000:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="PDF exports support at most 1000 rows",
        )
    bounded_days = max(1, min(int(days), 90))
    filters = {
        "days": bounded_days,
        "limit": bounded_limit,
        "site_url": str(site_url or "")[:2048],
    }
    fingerprint = _request_fingerprint(
        format=format,
        source_kind=source_kind,
        limit=bounded_limit,
        days=bounded_days,
        site_url=str(filters["site_url"] or "") or None,
    )
    row = await pool.fetchrow(
        """
        INSERT INTO export_jobs (
            tenant_id, format, status, source_kind, idempotency_key,
            request_fingerprint, filters, content_type, max_attempts,
            next_attempt_at, created_by_actor_id
        )
        VALUES ($1::uuid, $2, 'queued', $3, $4, $5, $6::jsonb, $7, $8, NOW(), $9::uuid)
        ON CONFLICT (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL
        DO NOTHING
        RETURNING id::text, tenant_id::text, format, status, source_kind,
                  idempotency_key, request_fingerprint, object_key,
                  filters,
                  checksum_sha256, byte_size, content_type, error, attempts,
                  max_attempts, next_attempt_at, created_by_actor_id::text,
                  created_at, completed_at, expires_at
        """,
        str(tenant_id),
        format,
        source_kind,
        idempotency_key,
        fingerprint,
        json.dumps(filters),
        _CONTENT_TYPES[format],
        settings.EXPORT_MAX_ATTEMPTS,
        user.user_id,
    )
    duplicate = row is None
    if row is None:
        row = await _fetch_job_row(pool, tenant_id=tenant_id, idempotency_key=idempotency_key)
        if row is None:
            raise RuntimeError("export idempotency conflict without an existing job")
        if row["request_fingerprint"] != fingerprint:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="idempotency_key was already used with different export parameters",
            )
    return {"ok": True, "duplicate": duplicate, "job": _job_dict(row)}


# Compatibility name retained for existing callers; work is now durable/queued.
create_and_run_export = create_export_job


async def list_jobs(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    limit: int = 50,
) -> list[dict[str, Any]]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"exports:read"}),
    )
    await ensure_export_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, format, status, source_kind,
               idempotency_key, request_fingerprint, object_key,
               filters,
               checksum_sha256, byte_size, content_type, error, attempts,
               max_attempts, next_attempt_at, created_by_actor_id::text,
               created_at, completed_at, expires_at
        FROM export_jobs
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC, id DESC
        LIMIT $2
        """,
        str(tenant_id),
        max(1, min(limit, 200)),
    )
    return [_job_dict(row) for row in rows]


async def get_job(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    job_id: UUID,
) -> dict[str, Any] | None:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"exports:read"}),
    )
    await ensure_export_schema(pool)
    row = await _fetch_job_row(pool, tenant_id=tenant_id, job_id=job_id)
    return _job_dict(row) if row else None


async def create_download(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    job_id: UUID,
) -> dict[str, Any]:
    job = await get_job(pool, user=user, tenant_id=tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="export job not found")
    if job["status"] != "completed" or not job["object_key"]:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="export artifact is not ready")
    expires_at = job.get("expires_at")
    remaining_seconds = object_storage.DEFAULT_PRESIGN_SECONDS
    if expires_at is not None:
        remaining_seconds = int((expires_at - datetime.now(UTC)).total_seconds())
        if remaining_seconds <= 0:
            raise HTTPException(status.HTTP_410_GONE, detail="export artifact has expired")
        remaining_seconds = min(remaining_seconds, object_storage.DEFAULT_PRESIGN_SECONDS)
    if not object_storage.is_configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="signed export downloads require object storage",
        )
    filename = f"forjd-export-{str(job_id)[:8]}.{job['format']}"
    url = await asyncio.to_thread(
        object_storage.generate_presigned_get,
        key=str(job["object_key"]),
        expires_in=remaining_seconds,
        filename=filename,
        content_type=str(job["content_type"]),
    )
    return {
        "url": url,
        "filename_hint": filename,
        "expires_in": remaining_seconds,
        "checksum_sha256": job["checksum_sha256"],
        "byte_size": job["byte_size"],
    }


# --- Tenant-initiated export removal ---
async def delete_job(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    job_id: UUID,
) -> dict[str, Any]:
    """Remove an export job row and best-effort delete its artifact."""
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"exports:write"}),
    )
    await ensure_export_schema(pool)
    row = await _fetch_job_row(pool, tenant_id=tenant_id, job_id=job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="export job not found")
    object_key = str(row["object_key"] or "")
    if object_key:
        try:
            await _delete_artifact(object_key)
        except object_storage.ObjectStorageNotConfiguredError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="export artifact exists but object storage is unavailable",
            ) from exc
        except Exception as exc:  # noqa: BLE001 - surface storage failures to the client
            logger.exception("export artifact delete failed id=%s", job_id)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="failed to delete export artifact",
            ) from exc
    result = await pool.execute(
        """
        DELETE FROM export_jobs
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        """,
        str(job_id),
        str(tenant_id),
    )
    if not str(result).endswith(" 1"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="export job not found")
    return {"ok": True, "id": str(job_id)}


async def tick_export_jobs(
    pool: asyncpg.Pool,
    *,
    batch_size: int = 5,
    worker_id: UUID | None = None,
    health: WorkerHealthRegistry | None = None,
) -> int:
    """Claim and process a small export batch; safe across API replicas."""
    await ensure_export_schema(pool)
    owner = worker_id or uuid4()
    await pool.execute(
        """
        UPDATE export_jobs
        SET status = CASE WHEN attempts >= max_attempts THEN 'failed'
                          ELSE 'retry_scheduled' END,
            next_attempt_at = NOW(), lease_owner = NULL, lease_expires_at = NULL,
            error = COALESCE(error, 'WorkerLeaseExpired'),
            completed_at = CASE WHEN attempts >= max_attempts THEN NOW() ELSE completed_at END
        WHERE status = 'running'
          AND (lease_expires_at IS NULL OR lease_expires_at <= NOW())
        """
    )
    claim_limit = max(1, min(batch_size, 25))
    processed = 0
    for _ in range(claim_limit):
        # Claim just in time. Export rendering and object storage are variable
        # latency operations; pre-leasing a serial batch lets later rows expire
        # before this worker can even start them.
        rows = await pool.fetch(
            """
            WITH candidates AS (
              SELECT id
              FROM export_jobs
              WHERE status IN ('queued', 'retry_scheduled')
                AND attempts < max_attempts
                AND next_attempt_at <= NOW()
                AND (lease_expires_at IS NULL OR lease_expires_at <= NOW())
              ORDER BY created_at, id
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            UPDATE export_jobs AS job
            SET status = 'running', lease_owner = $1::uuid,
                lease_expires_at = NOW() + ($2::text || ' seconds')::interval,
                attempts = attempts + 1, error = NULL
            FROM candidates
            WHERE job.id = candidates.id
            RETURNING job.id::text, job.tenant_id::text, job.format,
                      job.source_kind, job.filters, job.attempts, job.max_attempts,
                      job.object_key
            """,
            str(owner),
            str(_EXPORT_LEASE_SECONDS),
        )
        if not rows:
            break
        row = rows[0]
        await _process_claimed_job(pool, owner=owner, row=row, health=health)
        processed += 1
    await _expire_artifacts(pool)
    return processed


async def run_export_worker(
    pool: asyncpg.Pool,
    stop_event: asyncio.Event,
    *,
    interval_seconds: float | None = None,
    health: WorkerHealthRegistry | None = None,
) -> None:
    interval = interval_seconds or settings.EXPORT_WORKER_INTERVAL_SECONDS
    owner = uuid4()
    logger.info("export worker started owner=%s", owner)
    while not stop_event.is_set():
        try:
            processed = await tick_export_jobs(pool, worker_id=owner, health=health)
            if health is not None:
                health.succeeded("exports")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - supervised retry loop
            logger.exception("export worker tick failed")
            if health is not None:
                health.failed("exports", exc)
            processed = 0
        delay = 0.05 if processed else interval
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=delay)


async def _process_claimed_job(
    pool: asyncpg.Pool,
    *,
    owner: UUID,
    row: asyncpg.Record,
    health: WorkerHealthRegistry | None = None,
) -> None:
    job_id = str(row["id"])
    tenant_id = UUID(str(row["tenant_id"]))
    durable_object_key = str(row["object_key"] or "") or None
    heartbeat_stop = asyncio.Event()
    lease_lost = asyncio.Event()
    heartbeat = asyncio.create_task(
        _heartbeat_export_lease(
            pool,
            job_id=job_id,
            owner=owner,
            stop_event=heartbeat_stop,
            lease_lost=lease_lost,
            health=health,
        ),
        name=f"export-lease-{job_id}",
    )
    try:
        # A prior worker may have crashed after reserving the key or uploading
        # the object. The durable pointer lets retries and tenant erasure find
        # that artifact. Clean it before reserving this attempt's unique key.
        if durable_object_key:
            await _delete_artifact(durable_object_key)
            cleared = await pool.execute(
                """
                UPDATE export_jobs
                SET object_key = NULL
                WHERE id = $1::uuid AND lease_owner = $2::uuid AND object_key = $3
                """,
                job_id,
                str(owner),
                durable_object_key,
            )
            if not str(cleared).endswith(" 1"):
                logger.warning("export lease lost during stale artifact cleanup job=%s", job_id)
                return
            durable_object_key = None
        filters = _json_object(row["filters"])
        source_rows = await _load_source_rows_bounded(
            pool,
            tenant_id=tenant_id,
            source_kind=str(row["source_kind"]),
            filters=filters,
            limit=int(filters.get("limit") or 10_000),
        )
        artifact = await asyncio.to_thread(_render_export, source_rows, str(row["format"]))
        if len(artifact) > settings.EXPORT_MAX_ARTIFACT_BYTES:
            raise ValueError("export artifact exceeds the configured byte limit")
        digest = hashlib.sha256(artifact).hexdigest()
        durable_object_key = _artifact_key(
            tenant_id=tenant_id,
            job_id=job_id,
            format=str(row["format"]),
            artifact_version=f"{int(row['attempts'])}-{owner}",
        )
        if lease_lost.is_set():
            logger.warning("export lease lost before artifact planning job=%s", job_id)
            return
        planned = await pool.execute(
            """
            UPDATE export_jobs
            SET object_key = $3
            WHERE id = $1::uuid AND lease_owner = $2::uuid
            """,
            job_id,
            str(owner),
            durable_object_key,
        )
        if not str(planned).endswith(" 1"):
            logger.warning("export lease lost before artifact upload job=%s", job_id)
            return
        renewed = await _renew_export_lease(pool, job_id=job_id, owner=owner)
        if not renewed or lease_lost.is_set():
            logger.warning("export lease lost at artifact upload boundary job=%s", job_id)
            return
        await _store_artifact(
            artifact,
            tenant_id=tenant_id,
            job_id=job_id,
            format=str(row["format"]),
            checksum=digest,
            artifact_version=f"{int(row['attempts'])}-{owner}",
            object_key=durable_object_key,
        )
        updated = await pool.execute(
            """
            UPDATE export_jobs
            SET status = 'completed', object_key = $3,
                checksum_sha256 = $4, byte_size = $5,
                completed_at = NOW(),
                expires_at = NOW() + ($6::text || ' seconds')::interval,
                lease_owner = NULL, lease_expires_at = NULL,
                next_attempt_at = NOW(), error = NULL
            WHERE id = $1::uuid AND lease_owner = $2::uuid
            """,
            job_id,
            str(owner),
            durable_object_key,
            digest,
            len(artifact),
            # $6 is cast ::text — asyncpg rejects int for text params.
            str(settings.EXPORT_TTL_SECONDS),
        )
        if not str(updated).endswith(" 1"):
            # Every attempt has a unique key, so lease-loss cleanup cannot
            # delete a later worker's winning artifact.
            await _delete_artifact(durable_object_key)
            logger.warning("export lease lost after upload job=%s", job_id)
    except Exception as exc:  # noqa: BLE001 - durable job boundary
        logger.exception("export job failed id=%s", job_id)
        cleanup_succeeded = False
        if durable_object_key:
            try:
                await _delete_artifact(durable_object_key)
            except Exception:  # noqa: BLE001 - retain pointer for retry/erasure
                logger.exception("export artifact cleanup failed id=%s", job_id)
            else:
                cleanup_succeeded = True
        await pool.execute(
            """
            UPDATE export_jobs
            SET status = CASE WHEN attempts >= max_attempts THEN 'failed'
                              ELSE 'retry_scheduled' END,
                error = $3,
                next_attempt_at = NOW() + (
                  LEAST(3600, POWER(2, LEAST(attempts, 11))::integer)::text || ' seconds'
                )::interval,
                object_key = CASE
                  WHEN $4::boolean AND object_key = $5::text THEN NULL
                  ELSE object_key
                END,
                lease_owner = NULL, lease_expires_at = NULL,
                completed_at = CASE WHEN attempts >= max_attempts THEN NOW() ELSE NULL END
            WHERE id = $1::uuid AND lease_owner = $2::uuid
            """,
            job_id,
            str(owner),
            type(exc).__name__[:128],
            cleanup_succeeded,
            durable_object_key,
        )
    finally:
        heartbeat_stop.set()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat


async def _renew_export_lease(pool: asyncpg.Pool, *, job_id: str, owner: UUID) -> bool:
    result = await pool.execute(
        """
        UPDATE export_jobs
        SET lease_expires_at = NOW() + ($3::text || ' seconds')::interval
        WHERE id = $1::uuid AND status = 'running' AND lease_owner = $2::uuid
        """,
        job_id,
        str(owner),
        str(_EXPORT_LEASE_SECONDS),
    )
    return str(result).endswith(" 1")


async def _heartbeat_export_lease(
    pool: asyncpg.Pool,
    *,
    job_id: str,
    owner: UUID,
    stop_event: asyncio.Event,
    lease_lost: asyncio.Event,
    health: WorkerHealthRegistry | None = None,
) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_EXPORT_HEARTBEAT_SECONDS)
            return
        except TimeoutError:
            pass
        try:
            renewed = await asyncio.wait_for(
                _renew_export_lease(pool, job_id=job_id, owner=owner),
                timeout=10,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - retry while the current lease remains valid
            logger.exception("export lease heartbeat failed job=%s", job_id)
            continue
        if not renewed:
            lease_lost.set()
            return
        if health is not None:
            health.succeeded("exports")


async def _load_source_rows(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    source_kind: str,
    filters: dict[str, Any],
    limit: int,
    offset: int = 0,
) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 100_000))
    bounded_offset = max(0, min(offset, 100_000))
    # $2 is cast ::text in every query below — asyncpg rejects int for text params.
    days = str(max(1, min(int(filters.get("days") or 7), 90)))
    site_url = str(filters.get("site_url") or "")[:2048]
    if source_kind == "stream_results":
        rows = await pool.fetch(
            """
            SELECT id::text, tenant_id::text, kind, score, is_anomaly, features, created_at
            FROM stream_results
            WHERE tenant_id = $1::uuid
              AND created_at >= NOW() - ($2::text || ' days')::interval
            ORDER BY created_at DESC, id DESC LIMIT $3 OFFSET $4
            """,
            str(tenant_id),
            days,
            bounded_limit,
            bounded_offset,
        )
    elif source_kind == "analytics":
        rows = await pool.fetch(
            """
            SELECT id::text, tenant_id::text, bucket_start, bucket_size,
                   total_requests, avg_latency_ms, p99_latency_ms,
                   error_rate_percent, threats_detected, active_incidents,
                   unique_visitors, created_at
            FROM aggregated_analytics
            WHERE tenant_id = $1::uuid
              AND bucket_start >= NOW() - ($2::text || ' days')::interval
            ORDER BY bucket_start DESC, id DESC LIMIT $3 OFFSET $4
            """,
            str(tenant_id),
            days,
            bounded_limit,
            bounded_offset,
        )
    elif source_kind == "threat":
        rows = await pool.fetch(
            """
            SELECT id::text, tenant_id::text, source, host(ip_address) AS ip_address,
                   location, abuse_confidence_score, otx_pulses, is_malicious, created_at
            FROM threat_intelligence
            WHERE tenant_id = $1::uuid AND is_platform = FALSE
              AND created_at >= NOW() - ($2::text || ' days')::interval
            ORDER BY created_at DESC, id DESC LIMIT $3 OFFSET $4
            """,
            str(tenant_id),
            days,
            bounded_limit,
            bounded_offset,
        )
    elif source_kind == "lighthouse":
        rows = await pool.fetch(
            """
            SELECT id::text, tenant_id::text, url, scanned_at, performance,
                   accessibility, best_practices, seo, created_at
            FROM lighthouse_scans
            WHERE tenant_id = $1::uuid
              AND scanned_at >= NOW() - ($2::text || ' days')::interval
              AND ($3::text = '' OR url = $3)
            ORDER BY scanned_at DESC, id DESC LIMIT $4 OFFSET $5
            """,
            str(tenant_id),
            days,
            site_url,
            bounded_limit,
            bounded_offset,
        )
    elif source_kind == "vulnerabilities":
        rows = await pool.fetch(
            """
            SELECT id::text, tenant_id::text, asset_id::text, title, description,
                   status, severity, impact, likelihood, cve_id, created_at, updated_at
            FROM vulnerabilities
            WHERE tenant_id = $1::uuid
              AND created_at >= NOW() - ($2::text || ' days')::interval
            ORDER BY created_at DESC, id DESC LIMIT $3 OFFSET $4
            """,
            str(tenant_id),
            days,
            bounded_limit,
            bounded_offset,
        )
    else:
        raise ValueError(f"unsupported source_kind: {source_kind}")
    return [_exportable_row(row) for row in rows]


async def _load_source_rows_bounded(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    source_kind: str,
    filters: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    """Read a stable snapshot in bounded pages and enforce a memory budget."""
    bounded_limit = max(1, min(limit, 100_000))
    byte_budget = min(settings.EXPORT_MAX_SOURCE_BYTES, settings.EXPORT_MAX_ARTIFACT_BYTES)
    collected: list[dict[str, Any]] = []
    source_bytes = 0
    async with (
        pool.acquire() as connection,
        connection.transaction(isolation="repeatable_read", readonly=True),
    ):
        while len(collected) < bounded_limit:
            page_limit = min(_SOURCE_PAGE_ROWS, bounded_limit - len(collected))
            page = await _load_source_rows(
                connection,
                tenant_id=tenant_id,
                source_kind=source_kind,
                filters=filters,
                limit=page_limit,
                offset=len(collected),
            )
            if not page:
                break
            for item in page:
                source_bytes += len(
                    json.dumps(
                        item,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode()
                )
                if source_bytes > byte_budget:
                    raise ExportSourceTooLargeError(
                        "export source exceeds the configured in-memory byte budget; "
                        "narrow the filters or use a dedicated worker with a larger budget"
                    )
            collected.extend(page)
            if len(page) < page_limit:
                break
    return collected


def _render_export(rows: list[dict[str, Any]], format: str) -> bytes:
    frame = pl.DataFrame(rows) if rows else pl.DataFrame({"id": []})
    if format == "csv":
        return frame.write_csv().encode()
    if format == "json":
        return frame.write_json().encode()
    if format == "parquet":
        buffer = io.BytesIO()
        frame.write_parquet(buffer)
        return buffer.getvalue()
    if format == "pdf":
        from app.services.pdf_report import render_pdf_report

        if len(rows) > 1_000:
            raise ValueError("PDF exports support at most 1000 rows")
        return render_pdf_report(rows, title="FORJD Tenant Export")
    raise ValueError(f"unsupported format: {format}")


async def _store_artifact(
    artifact: bytes,
    *,
    tenant_id: UUID,
    job_id: str,
    format: str,
    checksum: str,
    artifact_version: str,
    object_key: str | None = None,
) -> str:
    key = object_key or _artifact_key(
        tenant_id=tenant_id,
        job_id=job_id,
        format=format,
        artifact_version=artifact_version,
    )
    if key.startswith("local:"):
        path = Path(key.removeprefix("local:"))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        await asyncio.to_thread(temporary.write_bytes, artifact)
        await asyncio.to_thread(os.replace, temporary, path)
        return key
    if not object_storage.is_configured():
        raise object_storage.ObjectStorageNotConfiguredError(
            "durable export object storage is not configured"
        )
    await asyncio.to_thread(
        object_storage.put_bytes,
        key=key,
        body=artifact,
        content_type=_CONTENT_TYPES[format],
        metadata={"sha256": checksum, "tenant": str(tenant_id), "job": job_id},
    )
    return key


def _artifact_key(
    *,
    tenant_id: UUID,
    job_id: str,
    format: str,
    artifact_version: str,
) -> str:
    safe_version = "".join(
        character for character in artifact_version if character.isalnum() or character in "-_"
    )[:96]
    if not safe_version:
        raise ValueError("export artifact version is required")
    filename = f"forjd-export-{job_id}-{safe_version}.{format}"
    if object_storage.is_configured():
        return object_storage.export_object_key(
            tenant_id=str(tenant_id), job_id=job_id, filename=filename
        )
    if settings.is_production:
        raise object_storage.ObjectStorageNotConfiguredError(
            "durable export object storage is required in production"
        )
    base = Path(settings.ML_MODEL_DIR).parent / "exports" / str(tenant_id)
    path = base / filename
    return f"local:{path.resolve()}"


async def _delete_artifact(object_key: str) -> None:
    if object_key.startswith("local:"):
        path = Path(object_key.removeprefix("local:"))
        await asyncio.to_thread(path.unlink, missing_ok=True)
    elif object_key:
        if not object_storage.is_configured():
            raise object_storage.ObjectStorageNotConfiguredError(
                "export artifact exists but object storage is unavailable"
            )
        await asyncio.to_thread(object_storage.delete_object, key=object_key)


async def _expire_artifacts(pool: asyncpg.Pool, *, limit: int = 50) -> int:
    rows = await pool.fetch(
        """
        SELECT id::text, object_key, status
        FROM export_jobs
        WHERE object_key IS NOT NULL
          AND next_attempt_at <= NOW()
          AND (
            (status = 'completed' AND expires_at <= NOW())
            OR status = 'failed'
          )
        ORDER BY COALESCE(expires_at, next_attempt_at), id
        LIMIT $1
        """,
        max(1, min(limit, 200)),
    )
    expired = 0
    for row in rows:
        try:
            await _delete_artifact(str(row["object_key"]))
            if row["status"] == "completed":
                result = await pool.execute(
                    """
                    UPDATE export_jobs
                    SET status = 'expired', object_key = NULL
                    WHERE id = $1::uuid AND status = 'completed' AND expires_at <= NOW()
                    """,
                    row["id"],
                )
            else:
                result = await pool.execute(
                    """
                    UPDATE export_jobs
                    SET object_key = NULL
                    WHERE id = $1::uuid AND status = 'failed' AND object_key = $2
                    """,
                    row["id"],
                    row["object_key"],
                )
            expired += int(str(result).endswith(" 1"))
        except Exception:  # noqa: BLE001 - retry cleanup on next tick
            logger.exception("expired export cleanup failed id=%s", row["id"])
            await pool.execute(
                """
                UPDATE export_jobs
                SET next_attempt_at = NOW() + INTERVAL '5 minutes'
                WHERE id = $1::uuid AND object_key = $2
                """,
                row["id"],
                row["object_key"],
            )
    return expired


async def _fetch_job_row(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    job_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT id::text, tenant_id::text, format, status, source_kind,
               idempotency_key, request_fingerprint, object_key,
               filters,
               checksum_sha256, byte_size, content_type, error, attempts,
               max_attempts, next_attempt_at, created_by_actor_id::text,
               created_at, completed_at, expires_at
        FROM export_jobs
        WHERE tenant_id = $1::uuid
          AND ($2::uuid IS NULL OR id = $2::uuid)
          AND ($3::text IS NULL OR idempotency_key = $3)
        """,
        str(tenant_id),
        str(job_id) if job_id else None,
        idempotency_key,
    )


def _job_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "format": row["format"],
        "status": row["status"],
        "source_kind": row["source_kind"],
        "idempotency_key": row["idempotency_key"],
        "filters": _json_object(row["filters"]),
        "object_key": row["object_key"],
        "checksum_sha256": row["checksum_sha256"],
        "byte_size": int(row["byte_size"] or 0),
        "content_type": row["content_type"],
        "error": row["error"],
        "attempts": int(row["attempts"] or 0),
        "max_attempts": int(row["max_attempts"] or 0),
        "next_attempt_at": row["next_attempt_at"],
        "created_by_actor_id": row["created_by_actor_id"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "expires_at": row["expires_at"],
        "download_ready": row["status"] == "completed" and bool(row["object_key"]),
    }


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _exportable_row(row: asyncpg.Record) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in dict(row).items():
        if isinstance(value, (dict, list)):
            result[key] = json.dumps(value, sort_keys=True, separators=(",", ":"))
        elif hasattr(value, "isoformat"):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result
