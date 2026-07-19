"""Tenant-scoped report documents — durable partner report storage."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status

from app.core.auth import AuthUser
from app.core.config import settings
from app.models.reports import CreateReportDocumentRequest
from app.services import audit
from app.services import tenants as tenant_svc


# --- Schema (development soft-migrate; production applies sql/022) ---
async def ensure_report_documents_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    if not settings.SOFT_MIGRATE_SCHEMA:
        secure = await pool.fetchval(
            """
            SELECT EXISTS (
              SELECT 1 FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relname = 'report_documents'
                AND c.relrowsecurity = TRUE
            )
            """
        )
        if not secure:
            raise RuntimeError("secure report_documents schema missing; apply backend/sql/022")
        return
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS report_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            client_report_id UUID NOT NULL,
            content_sha256 TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'issue_report',
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            context JSONB NOT NULL DEFAULT '{}'::jsonb,
            submitted_by_pseudonym TEXT,
            created_by_actor_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (kind ~ '^[a-z][a-z0-9_.-]{0,63}$'),
            CHECK (char_length(title) BETWEEN 1 AND 255),
            CHECK (char_length(body) <= 8000),
            CHECK (jsonb_typeof(context) = 'object')
        )
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS report_documents_tenant_created_idx
        ON report_documents (tenant_id, created_at DESC, id DESC)
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS report_documents_tenant_client_idx
        ON report_documents (tenant_id, client_report_id)
        """
    )


def _document_dict(row: asyncpg.Record) -> dict[str, Any]:
    context = row["context"]
    if isinstance(context, str):
        context = json.loads(context)
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "client_report_id": row["client_report_id"],
        "kind": row["kind"],
        "title": row["title"],
        "body": row["body"],
        "context": context,
        "submitted_by_pseudonym": row["submitted_by_pseudonym"],
        "created_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else str(row["created_at"]),
    }


def _content_fingerprint(document: CreateReportDocumentRequest) -> str:
    canonical = json.dumps(
        {
            "kind": document.kind,
            "title": document.title,
            "body": document.body,
            "context": document.context,
            "submitted_by_pseudonym": document.submitted_by_pseudonym,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


# --- Create ---
async def create_document(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    document: CreateReportDocumentRequest,
) -> dict[str, Any]:
    tenant_id = document.tenant_id
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"reports:write"}),
    )
    await ensure_report_documents_schema(pool)
    content_sha256 = _content_fingerprint(document)
    row = await pool.fetchrow(
        """
        INSERT INTO report_documents (
            tenant_id, client_report_id, content_sha256, kind, title, body, context,
            submitted_by_pseudonym, created_by_actor_id
        )
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7::jsonb, $8, $9::uuid)
        ON CONFLICT (tenant_id, client_report_id) DO NOTHING
        RETURNING id::text, tenant_id::text, client_report_id::text,
                  content_sha256, kind, title, body, context,
                  submitted_by_pseudonym, created_at
        """,
        str(tenant_id),
        str(document.client_report_id),
        content_sha256,
        document.kind,
        document.title,
        document.body,
        json.dumps(document.context),
        document.submitted_by_pseudonym,
        user.user_id,
    )
    duplicate = row is None
    if row is None:
        row = await pool.fetchrow(
            """
            SELECT id::text, tenant_id::text, client_report_id::text,
                   content_sha256, kind, title, body, context,
                   submitted_by_pseudonym, created_at
            FROM report_documents
            WHERE tenant_id = $1::uuid AND client_report_id = $2::uuid
            """,
            str(tenant_id),
            str(document.client_report_id),
        )
        if row is None:
            raise RuntimeError("report idempotency conflict without an existing row")
        if row["content_sha256"] != content_sha256:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="client_report_id was already used with different content",
            )
    item = _document_dict(row)
    if not duplicate:
        await audit.record(
            pool,
            action="reports.document.create",
            actor_user_id=user.actor_id,
            tenant_id=tenant_id,
            resource_type="report_document",
            resource_id=item["id"],
            details={"kind": document.kind, "body_length": len(document.body)},
        )
    return {"ok": True, "duplicate": duplicate, "document": item}


# --- List ---
async def list_documents(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    kind: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"reports:read"}),
    )
    await ensure_report_documents_schema(pool)
    clauses = ["tenant_id = $1::uuid"]
    params: list[Any] = [str(tenant_id)]
    if kind:
        params.append(kind)
        clauses.append(f"kind = ${len(params)}")
    params.append(max(1, min(limit, 500)))
    rows = await pool.fetch(
        f"""
        SELECT id::text, tenant_id::text, client_report_id::text,
               content_sha256, kind, title, body, context,
               submitted_by_pseudonym, created_at
        FROM report_documents
        WHERE {" AND ".join(clauses)}
        ORDER BY created_at DESC, id DESC
        LIMIT ${len(params)}
        """,
        *params,
    )
    return {"ok": True, "documents": [_document_dict(row) for row in rows]}
