"""PDF report generation + optional object-storage upload."""

from __future__ import annotations

import contextlib
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg

from app.core import object_storage
from app.core.auth import AuthUser
from app.core.config import settings
from app.services import tenants as tenant_svc
from app.services.pdf_report import render_pdf_report


async def ensure_report_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS report_archives (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            object_key TEXT,
            checksum_sha256 TEXT,
            row_count INT NOT NULL DEFAULT 0,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by_actor_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


async def generate_stream_report(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    title: str = "FORJD Stream Report",
    limit: int = 500,
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin", "member"}),
    )
    await ensure_report_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, kind, score, is_anomaly, created_at
        FROM stream_results
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        str(tenant_id),
        max(1, min(limit, 1000)),
    )
    table_rows = [
        {
            "id": r["id"],
            "kind": r["kind"],
            "score": r["score"],
            "is_anomaly": r["is_anomaly"],
            "created_at": r["created_at"].isoformat()
            if hasattr(r["created_at"], "isoformat")
            else str(r["created_at"]),
        }
        for r in rows
    ]
    pdf_bytes = render_pdf_report(
        table_rows,
        title=title,
        metadata={"tenant_id": str(tenant_id), "generator": "forjd"},
    )
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"report_{stamp}.pdf"
    object_key: str | None = None
    if object_storage.is_configured():
        object_key = object_storage.export_object_key(
            tenant_id=str(tenant_id), job_id=digest[:12], filename=filename
        )
        object_storage.put_bytes(
            key=object_key, body=pdf_bytes, content_type="application/pdf"
        )
    else:
        out_dir = Path(settings.ML_MODEL_DIR).parent / "reports" / str(tenant_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / filename
        path.write_bytes(pdf_bytes)
        object_key = str(path)

    row = await pool.fetchrow(
        """
        INSERT INTO report_archives (
            tenant_id, title, object_key, checksum_sha256, row_count,
            metadata, created_by_actor_id
        )
        VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb, $7::uuid)
        RETURNING id::text, tenant_id::text, title, object_key, checksum_sha256,
                  row_count, created_at
        """,
        str(tenant_id),
        title,
        object_key,
        digest,
        len(table_rows),
        json.dumps({"format": "pdf"}),
        user.user_id,
    )
    result = {"ok": True, "report": dict(row), "bytes": len(pdf_bytes)}
    if object_storage.is_configured() and object_key and not object_key.startswith("/"):
        with contextlib.suppress(Exception):
            result["presigned_url"] = object_storage.generate_presigned_get(key=object_key)
    return result
