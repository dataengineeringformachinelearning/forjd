"""Secure E2EE telemetry ingestion — store ciphertext only, enqueue Prefect."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.core.crypto import CryptoError
from app.models.ingest import (
    EmbeddingIngestRequest,
    IngestBatchRequest,
    IngestEventRequest,
    IngestEventResult,
)
from app.pipelines.ingest import run_ingest_flow
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.ingest")


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.8g}" for x in embedding) + "]"


async def ingest_events(
    *,
    pool: asyncpg.Pool,
    user: AuthUser,
    batch: IngestBatchRequest,
) -> dict[str, Any]:
    await tenant_svc.ensure_secure_schema(pool)

    # All events in a batch must target tenants the user belongs to.
    tenant_ids = {e.tenant_id for e in batch.events}
    for tid in tenant_ids:
        await tenant_svc.require_member(
            pool,
            tenant_id=tid,
            user_id=user.user_id,
            min_roles=frozenset({"owner", "admin", "member"}),
        )

    results: list[IngestEventResult] = []
    for event in batch.events:
        results.append(await _insert_event(pool, user=user, event=event))

    prefect: dict[str, Any] | None = None
    try:
        prefect = run_ingest_flow(
            user_id=user.user_id,
            tenant_ids=[str(t) for t in tenant_ids],
            accepted=len(results),
            event_ids=[str(r.id) for r in results],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest prefect failed")
        prefect = {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "accepted": len(results),
        "results": results,
        "prefect": prefect,
    }


async def _insert_event(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    event: IngestEventRequest,
) -> IngestEventResult:
    try:
        sealed = event.envelope.to_sealed()
    except CryptoError as exc:
        raise ValueError(str(exc)) from exc

    # Idempotent insert — same client_event_id + hash is a no-op duplicate.
    row = await pool.fetchrow(
        """
        INSERT INTO telemetry_events (
            tenant_id, submitted_by, client_event_id, occurred_at,
            algo, key_id, ratchet_header, nonce, ciphertext, ciphertext_sha256,
            content_type, schema_version, metadata
        )
        VALUES (
            $1::uuid, $2::uuid, $3, $4,
            $5, $6, $7, $8, $9, $10,
            $11, $12, $13::jsonb
        )
        ON CONFLICT (tenant_id, client_event_id) DO NOTHING
        RETURNING id, tenant_id, client_event_id, created_at
        """,
        str(event.tenant_id),
        user.user_id,
        event.client_event_id,
        event.occurred_at,
        sealed.algo,
        sealed.key_id,
        sealed.ratchet_header,
        sealed.nonce,
        sealed.ciphertext,
        sealed.ciphertext_sha256,
        event.content_type,
        event.schema_version,
        json.dumps(event.metadata),
    )
    if row is not None:
        return IngestEventResult(
            id=row["id"],
            tenant_id=row["tenant_id"],
            client_event_id=row["client_event_id"],
            created_at=row["created_at"],
            duplicate=False,
        )

    existing = await pool.fetchrow(
        """
        SELECT id, tenant_id, client_event_id, created_at, ciphertext_sha256
        FROM telemetry_events
        WHERE tenant_id = $1::uuid AND client_event_id = $2
        """,
        str(event.tenant_id),
        event.client_event_id,
    )
    if existing is None:
        raise RuntimeError("ingest conflict without existing row")
    if existing["ciphertext_sha256"] != sealed.ciphertext_sha256:
        raise ValueError("client_event_id already used with different ciphertext")
    return IngestEventResult(
        id=existing["id"],
        tenant_id=existing["tenant_id"],
        client_event_id=existing["client_event_id"],
        created_at=existing["created_at"],
        duplicate=True,
    )


async def ingest_embedding(
    *,
    pool: asyncpg.Pool,
    user: AuthUser,
    body: EmbeddingIngestRequest,
) -> dict[str, Any]:
    await tenant_svc.ensure_secure_schema(pool)
    await tenant_svc.require_member(
        pool,
        tenant_id=body.tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin", "member"}),
    )

    emb_lit = _vector_literal(body.embedding) if body.embedding is not None else None
    row = await pool.fetchrow(
        """
        INSERT INTO embedding_vectors (
            tenant_id, telemetry_event_id, series_id, model_version,
            embedding, reconstruction_error, is_anomaly,
            context_ciphertext, context_nonce, context_key_id, metadata
        )
        VALUES (
            $1::uuid, $2::uuid, $3, $4,
            $5::vector, $6, $7,
            $8, $9, $10, $11::jsonb
        )
        RETURNING id::text, created_at
        """,
        str(body.tenant_id),
        str(body.telemetry_event_id) if body.telemetry_event_id else None,
        body.series_id,
        body.model_version,
        emb_lit,
        body.reconstruction_error,
        body.is_anomaly,
        body.context_ciphertext,
        body.context_nonce,
        body.context_key_id,
        json.dumps(body.metadata),
    )
    return {
        "ok": True,
        "id": row["id"],
        "created_at": row["created_at"].isoformat(),
        "tenant_id": str(body.tenant_id),
    }


async def list_recent_events(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    limit: int = 20,
) -> list[dict[str, Any]]:
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, client_event_id, created_at, occurred_at,
               algo, key_id, content_type, schema_version,
               ciphertext_sha256, metadata
        FROM telemetry_events
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        str(tenant_id),
        limit,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        meta = r["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        out.append(
            {
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "client_event_id": r["client_event_id"],
                "created_at": r["created_at"].isoformat(),
                "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else None,
                "algo": r["algo"],
                "key_id": r["key_id"],
                "content_type": r["content_type"],
                "schema_version": r["schema_version"],
                "ciphertext_sha256": r["ciphertext_sha256"],
                "metadata": meta,
                # Intentionally omit ciphertext / nonce / ratchet_header from list API
                # to reduce accidental leakage in logs/UI; fetch-by-id can add later.
            }
        )
    return out
