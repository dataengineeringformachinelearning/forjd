"""Batch data exports via Polars (CSV / JSON / Parquet) ."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import asyncpg
import polars as pl

from app.core.auth import AuthUser
from app.core.config import settings
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.exports")

ExportFormat = Literal["csv", "json", "parquet"]


# --- Soft schema ---
async def ensure_export_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
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


# --- Create + run export from stream_results ---
async def create_and_run_export(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    format: ExportFormat = "csv",
    source_kind: str = "stream_results",
    limit: int = 10_000,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"exports:write"}),
    )
    await ensure_export_schema(pool)
    job = await pool.fetchrow(
        """
        INSERT INTO export_jobs (
            tenant_id, format, status, source_kind, created_by_actor_id
        )
        VALUES ($1::uuid, $2, 'running', $3, $4::uuid)
        RETURNING id::text, tenant_id::text, format, status, source_kind, created_at
        """,
        str(tenant_id),
        format,
        source_kind,
        user.user_id,
    )
    job_id = str(job["id"])
    try:
        rows = await _load_source_rows(
            pool, tenant_id=tenant_id, source_kind=source_kind, limit=limit
        )
        path, checksum = _write_export(
            rows,
            tenant_id=tenant_id,
            job_id=job_id,
            format=format,
        )
        await pool.execute(
            """
            UPDATE export_jobs
            SET status = 'completed',
                object_key = $2,
                checksum_sha256 = $3,
                completed_at = NOW(),
                error = NULL
            WHERE id = $1::uuid
            """,
            job_id,
            str(path),
            checksum,
        )
        return {
            "ok": True,
            "job": await get_job(pool, user=user, tenant_id=tenant_id, job_id=UUID(job_id)),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("export job %s failed", job_id)
        await pool.execute(
            """
            UPDATE export_jobs
            SET status = 'failed', error = $2, completed_at = NOW()
            WHERE id = $1::uuid
            """,
            job_id,
            str(exc)[:2000],
        )
        return {
            "ok": False,
            "job": await get_job(pool, user=user, tenant_id=tenant_id, job_id=UUID(job_id)),
            "error": str(exc),
        }


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
        SELECT id::text, tenant_id::text, format, status, source_kind, object_key,
               checksum_sha256, error, created_by_actor_id::text, created_at, completed_at
        FROM export_jobs
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        str(tenant_id),
        max(1, min(limit, 200)),
    )
    return [_job_dict(r) for r in rows]


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
    row = await pool.fetchrow(
        """
        SELECT id::text, tenant_id::text, format, status, source_kind, object_key,
               checksum_sha256, error, created_by_actor_id::text, created_at, completed_at
        FROM export_jobs
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        """,
        str(job_id),
        str(tenant_id),
    )
    return _job_dict(row) if row else None


async def _load_source_rows(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    source_kind: str,
    limit: int,
) -> list[dict[str, Any]]:
    if source_kind != "stream_results":
        raise ValueError(f"unsupported source_kind: {source_kind}")
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, kind, score, is_anomaly, features, created_at
        FROM stream_results
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        str(tenant_id),
        max(1, min(limit, 100_000)),
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        features = r["features"]
        if isinstance(features, str):
            features = json.loads(features)
        out.append(
            {
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "kind": r["kind"],
                "score": r["score"],
                "is_anomaly": bool(r["is_anomaly"]),
                "features": json.dumps(features) if not isinstance(features, str) else features,
                "created_at": r["created_at"].isoformat()
                if hasattr(r["created_at"], "isoformat")
                else str(r["created_at"]),
            }
        )
    return out


def _write_export(
    rows: list[dict[str, Any]],
    *,
    tenant_id: UUID,
    job_id: str,
    format: ExportFormat,
) -> tuple[Path, str]:
    base = Path(settings.ML_MODEL_DIR).parent / "exports" / str(tenant_id)
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = base / f"{job_id}_{stamp}.{format}"
    df = pl.DataFrame(rows) if rows else pl.DataFrame({"id": []})
    if format == "csv":
        df.write_csv(path)
    elif format == "json":
        df.write_json(path)
    elif format == "parquet":
        df.write_parquet(path)
    else:
        raise ValueError(f"unsupported format: {format}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, digest


def _job_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "format": row["format"],
        "status": row["status"],
        "source_kind": row["source_kind"],
        "object_key": row["object_key"],
        "checksum_sha256": row["checksum_sha256"],
        "error": row["error"],
        "created_by_actor_id": row["created_by_actor_id"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
    }
