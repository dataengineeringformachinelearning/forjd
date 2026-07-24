"""Universal E2EE event ingestion — store ciphertext only, run configured workflows.

Ingest path guarantees:
  • Caller presents a verified principal (`get_current_user`): enterprise user JWT
    or tenant-scoped service token (subprocessor / M2M).
  • Tenant isolation checked before any write (`require_tenant_access`).
  • Envelope fields are validated but **never decrypted**.
  • Workflow YAML/JSON selects processor + thresholds (not product forks).
  • Prefect + Rust/Python processors receive metadata only; results land in `stream_results`.

How a partner SaaS calls FORJD as a subprocessor
----------------------------------------------------
1. Enterprise admin creates tenant + mints ``POST /api/v1/service-accounts``
   (``subprocessor`` label optional, e.g. ``\"partner-app\"``).
2. The partner stores ``fjsvc_…`` as a secret; every request uses
   ``Authorization: Bearer fjsvc_…`` and the bound ``tenant_id``.
3. Register crypto session (``POST /api/v1/sessions``) then
   ``POST /api/v1/ingest`` with AES-256-GCM envelopes.
4. Read scores via ``GET /api/v1/projections`` / ``GET /api/v1/ingest/results``
   or Supabase Realtime on ``stream_results`` / ``projection_feed``.
FORJD never accepts partner end-user tokens — only the service principal.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from app.core.auth import AuthUser
from app.core.config import settings
from app.core.crypto import CryptoError, b64decode
from app.models.ingest import (
    EmbeddingIngestRequest,
    IngestBatchRequest,
    IngestEventRequest,
    IngestEventResult,
)
from app.services import audit
from app.services import ingest_processing as processing_svc
from app.services import projections as proj_svc
from app.services import sessions as session_svc
from app.services import tenants as tenant_svc
from app.workflows.models import WorkflowDefinition
from app.workflows.registry import (
    canonical_event_type,
    canonical_workflow_id,
    resolve_workflow,
)

logger = logging.getLogger("forjd.ingest")


class IngestConflictError(ValueError):
    """A client id was reused with different immutable event content."""


# --- Helpers ---
def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.8g}" for x in embedding) + "]"


def _validate_encryption(event: IngestEventRequest, workflow: WorkflowDefinition) -> None:
    """Fail closed if client encryption is outside the workflow policy."""
    mode = event.encryption.mode
    algo = event.encryption.algo
    if mode not in workflow.encryption.modes:
        raise ValueError(f"encryption.mode={mode!r} not allowed for workflow {workflow.id!r}")
    if algo not in workflow.encryption.algos:
        raise ValueError(f"encryption.algo={algo!r} not allowed for workflow {workflow.id!r}")
    if event.envelope.algo != algo:
        raise ValueError("envelope.algo must match encryption.algo")


def _fingerprint_values(
    *,
    occurred_at: datetime | None,
    encryption_mode: str,
    algo: str,
    key_id: str,
    ratchet_header: str | None,
    nonce: str,
    ciphertext_sha256: str,
    ciphertext_bytes: int,
    content_type: str,
    event_type: str | None,
    schema_version: int,
    workflow_id: str,
    metadata: dict[str, Any],
) -> str:
    payload = {
        "occurred_at": occurred_at.isoformat() if occurred_at else None,
        "encryption_mode": encryption_mode,
        "algo": algo,
        "key_id": key_id,
        "ratchet_header": ratchet_header,
        "nonce": nonce,
        "ciphertext_sha256": ciphertext_sha256,
        "ciphertext_bytes": ciphertext_bytes,
        "content_type": content_type,
        "event_type": event_type,
        "schema_version": schema_version,
        "workflow_id": workflow_id,
        "metadata": metadata,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _event_fingerprint(
    event: IngestEventRequest,
    *,
    workflow_id: str,
    event_type: str | None,
    ciphertext_bytes: int,
) -> str:
    sealed = event.envelope.to_sealed()
    return _fingerprint_values(
        occurred_at=event.occurred_at,
        encryption_mode=event.encryption.mode,
        algo=sealed.algo,
        key_id=sealed.key_id,
        ratchet_header=sealed.ratchet_header,
        nonce=sealed.nonce,
        ciphertext_sha256=sealed.ciphertext_sha256,
        ciphertext_bytes=ciphertext_bytes,
        content_type=event.content_type,
        event_type=event_type,
        schema_version=event.schema_version,
        workflow_id=workflow_id,
        metadata=event.metadata,
    )


# --- Batch ingest (membership → resolve workflow → persist → Prefect) ---
async def ingest_events(
    *,
    pool: asyncpg.Pool,
    user: AuthUser,
    batch: IngestBatchRequest,
) -> dict[str, Any]:
    await tenant_svc.ensure_secure_schema(pool)

    tenant_ids = {e.tenant_id for e in batch.events}
    for tid in tenant_ids:
        await tenant_svc.require_tenant_access(
            pool,
            principal=user,
            tenant_id=tid,
            min_roles=frozenset({"owner", "admin", "member"}),
            required_scopes=frozenset({"ingest:write"}),
        )

    # Zero-trust: batch-check crypto sessions (one query, not N).
    await session_svc.require_active_sessions(
        pool,
        pairs={(e.tenant_id, e.envelope.key_id) for e in batch.events},
    )

    prepared: list[dict[str, Any]] = []
    for event in batch.events:
        workflow = resolve_workflow(
            content_type=event.content_type,
            event_type=event.event_type,
            workflow_id=event.workflow_id,
        )
        # Partner aliases → canonical event_type for storage / processors.
        stored_event_type = canonical_event_type(event.event_type) or event.event_type
        _validate_encryption(event, workflow)
        try:
            sealed = event.envelope.to_sealed()
            # Byte length of decoded ciphertext (not base64 char count).
            cipher_len = len(b64decode(sealed.ciphertext))
        except CryptoError as exc:
            raise ValueError(str(exc)) from exc
        prepared.append(
            {
                "event": event,
                "workflow": workflow,
                "event_type": stored_event_type,
                "sealed": sealed,
                "cipher_len": cipher_len,
                "fingerprint": _event_fingerprint(
                    event,
                    workflow_id=workflow.id,
                    event_type=stored_event_type,
                    ciphertext_bytes=cipher_len,
                ),
            }
        )

    # Acceptance and the metadata-only processing receipts are all-or-nothing.
    # Engine execution remains post-commit, but a crash can no longer orphan an
    # accepted event because the leased recovery worker owns the durable row.
    results: list[IngestEventResult] = []
    # A durable receipt is deliberately single-tenant and wire-shape
    # homogeneous. This keeps tenant erasure from discarding another tenant's
    # accepted work and preserves the exact content/event contract on retry.
    all_groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    new_groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    processing_receipts: list[dict[str, Any]] = []
    acceptance_id = uuid4()
    async with pool.acquire() as conn, conn.transaction():
        # The tuple checkpoint is only safe when a projector cannot pass an
        # older, still-uncommitted acceptance transaction. Acquire the exact
        # projector snapshot fences in a stable order before inserting and
        # stamp rows with monotonic statement time (Postgres NOW() is the
        # pre-wait transaction time).
        acceptance_leases = sorted(
            {
                proj_svc.projection_acceptance_fence_name(
                    tenant_id=item["event"].tenant_id,
                    projection_name=item["workflow"].pipeline.projection_name,
                    workflow_id=item["workflow"].id,
                )
                for item in prepared
            }
        )
        for lease_name in acceptance_leases:
            await conn.fetchval(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                lease_name,
            )
        for item in prepared:
            event = item["event"]
            workflow = item["workflow"]
            result = await _insert_event(
                conn,
                user=user,
                event=event,
                workflow=workflow,
                event_type=item["event_type"],
                sealed=item["sealed"],
                ciphertext_bytes=item["cipher_len"],
                fingerprint=item["fingerprint"],
            )
            results.append(result)
            # Preserve allowlisted routing tags for analytics charts (never ciphertext).
            routing = {
                key: value
                for key, value in (event.metadata or {}).items()
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
            }
            meta = {
                "event_id": str(result.id),
                "tenant_id": str(event.tenant_id),
                "key_id": event.envelope.key_id,
                "cipher_len": item["cipher_len"],
                "content_type": event.content_type,
                "event_type": item["event_type"] or "",
                "workflow_id": workflow.id,
                "created_at": result.created_at,
                "metadata": routing,
            }
            group_key = (
                workflow.id,
                str(event.tenant_id),
                event.content_type,
                item["event_type"] or "",
            )
            all_slot = all_groups.setdefault(
                group_key,
                {"workflow": workflow, "events": [], "content_type": "", "event_type": None},
            )
            all_slot["events"].append(meta)
            all_slot["content_type"] = event.content_type
            all_slot["event_type"] = item["event_type"]
            if not result.duplicate:
                new_slot = new_groups.setdefault(
                    group_key,
                    {
                        "workflow": workflow,
                        "events": [],
                        "content_type": "",
                        "event_type": None,
                    },
                )
                new_slot["events"].append(meta)
                new_slot["content_type"] = event.content_type
                new_slot["event_type"] = item["event_type"]

        for ordinal, group in enumerate(new_groups.values()):
            processing_receipts.append(
                await processing_svc.register_processing_batch(
                    conn,
                    acceptance_id=acceptance_id,
                    group_ordinal=ordinal,
                    requested_by=user.actor_id,
                    workflow=group["workflow"],
                    content_type=group["content_type"],
                    event_type=group["event_type"],
                    events=group["events"],
                )
            )

        # Compliance evidence is part of acceptance, not a post-commit side
        # effect. A missing/unavailable audit store therefore rolls back the
        # sealed events and their processing receipts together. Details remain
        # metadata-only and describe accepted state, not later processing.
        accepted_by_tenant: dict[UUID, dict[str, Any]] = {
            tid: {
                "accepted": 0,
                "new_events": 0,
                "duplicates": 0,
                "workflows": [],
                "processing_batch_ids": [],
            }
            for tid in tenant_ids
        }
        for item, result in zip(prepared, results, strict=True):
            tid = item["event"].tenant_id
            tenant_acceptance = accepted_by_tenant[tid]
            tenant_acceptance["accepted"] += 1
            tenant_acceptance["new_events"] += int(not result.duplicate)
            tenant_acceptance["duplicates"] += int(result.duplicate)
            workflow_id = item["workflow"].id
            if workflow_id not in tenant_acceptance["workflows"]:
                tenant_acceptance["workflows"].append(workflow_id)
        for receipt, group in zip(processing_receipts, new_groups.values(), strict=True):
            processing_id = str(receipt["id"])
            for tenant_id in {UUID(str(event["tenant_id"])) for event in group["events"]}:
                accepted_by_tenant[tenant_id]["processing_batch_ids"].append(processing_id)

        for tid in sorted(tenant_ids, key=str):
            tenant_acceptance = accepted_by_tenant[tid]
            await audit.record_required(
                conn,
                action=audit.ACTION_INGEST_BATCH,
                actor_user_id=user.actor_id,
                tenant_id=tid,
                resource_type="ingest_acceptance",
                resource_id=str(acceptance_id),
                details={
                    "acceptance_id": str(acceptance_id),
                    **tenant_acceptance,
                    "processing_receipts": len(tenant_acceptance["processing_batch_ids"]),
                    "principal_kind": user.kind.value,
                    "subprocessor": user.subprocessor or "",
                },
            )

    new_event_count = sum(not result.duplicate for result in results)
    processing_batch_ids = [str(receipt["id"]) for receipt in processing_receipts]
    if new_event_count == 0:
        # A lost response can be retried with the exact same event grouping.
        # Locate and wake the original receipt instead of creating or running a
        # different grouping under the current workflow configuration.
        for (workflow_id, _tenant_id, _content_type, _event_type), group in all_groups.items():
            prior_receipts = await processing_svc.find_processing_batches_covered_by_retry(
                pool,
                workflow_id=workflow_id,
                event_ids=[str(event["event_id"]) for event in group["events"]],
            )
            processing_batch_ids.extend(str(receipt["id"]) for receipt in prior_receipts)
        processing_batch_ids = list(dict.fromkeys(processing_batch_ids))
        await processing_svc.wake_processing_batches(
            pool,
            batch_ids=processing_batch_ids,
            revive_failed=True,
        )

    processing_outcomes = (
        await processing_svc.tick_ingest_processing(
            pool,
            batch_size=max(1, len(processing_batch_ids)),
            batch_ids=processing_batch_ids or None,
            _schema_ready=True,
        )
        if processing_batch_ids
        else []
    )
    processing_states = await processing_svc.fetch_processing_batch_states(
        pool,
        batch_ids=processing_batch_ids,
    )

    prefect_runs: list[dict[str, Any]] = [
        dict(outcome["prefect"])
        for outcome in processing_outcomes
        if isinstance(outcome.get("prefect"), dict)
    ]
    pathway_summary: dict[str, Any] = {
        "ok": all(bool(outcome.get("ok")) for outcome in processing_outcomes),
        "count": 0,
        "tenants": 0,
        "by_tenant": {},
        "anomaly_count": 0,
        "workflows": [],
    }
    persisted = sum(int(outcome.get("written") or 0) for outcome in processing_outcomes)
    dlq_enqueued = sum(int(outcome.get("dlq_enqueued") or 0) for outcome in processing_outcomes)
    for outcome in processing_outcomes:
        pathway = outcome.get("pathway") or {}
        pathway_summary["count"] += int(pathway.get("count") or 0)
        pathway_summary["anomaly_count"] += int(pathway.get("anomaly_count") or 0)
        if pathway.get("engine"):
            pathway_summary["engine"] = pathway.get("engine")
        workflow_id = pathway.get("workflow_id")
        if workflow_id and workflow_id not in pathway_summary["workflows"]:
            pathway_summary["workflows"].append(workflow_id)
        for tid, stats in (pathway.get("by_tenant") or {}).items():
            slot = pathway_summary["by_tenant"].setdefault(
                tid, {"count": 0, "bytes": 0, "max_cipher_len": 0}
            )
            slot["count"] += int(stats.get("count") or 0)
            slot["bytes"] += int(stats.get("bytes") or 0)
            slot["max_cipher_len"] = max(
                slot["max_cipher_len"], int(stats.get("max_cipher_len") or 0)
            )
    pathway_summary["tenants"] = len(pathway_summary["by_tenant"])

    durable_statuses = {str(row["status"]) for row in processing_states}
    processing_ok = not processing_batch_ids or durable_statuses == {"completed"}
    pathway_summary["ok"] = processing_ok
    if not processing_batch_ids:
        processing_state = "not_required"
        recovery_state = "not_required"
    elif processing_ok:
        processing_state = "completed"
        recovery_state = "completed"
    else:
        processing_state = "failed"
        recovery_state = next(
            (
                status
                for status in ("failed", "retry_scheduled", "running", "queued")
                if status in durable_statuses
            ),
            "retry_scheduled",
        )

    return {
        "ok": processing_ok,
        "accepted": len(results),
        "new_events": new_event_count,
        "duplicates": sum(r.duplicate for r in results),
        "results": results,
        "pathway": pathway_summary,
        "stream_results_written": persisted,
        "dlq_enqueued": dlq_enqueued,
        "processing_state": processing_state,
        "processing_recovery_state": recovery_state,
        "processing_batches": [
            {
                "id": str(state["id"]),
                "status": str(state["status"]),
                "attempts": int(state["attempts"]),
                "max_attempts": int(state["max_attempts"]),
                "status_path": (
                    f"{settings.API_V1_STR.rstrip('/')}/ingest/processing/{state['id']}"
                ),
            }
            for state in processing_states
        ],
        "processing_mode": "synchronous",
        "async_processing_available": False,
        "durable_processing_recovery": True,
        "prefect": (
            prefect_runs[0]
            if len(prefect_runs) == 1
            else {"ok": processing_ok, "runs": prefect_runs}
        ),
    }


# --- Single-event persist (idempotent; never decrypts) ---
async def _insert_event(
    pool: asyncpg.Pool | asyncpg.Connection,
    *,
    user: AuthUser,
    event: IngestEventRequest,
    workflow: WorkflowDefinition,
    event_type: str | None = None,
    sealed: Any | None = None,
    ciphertext_bytes: int | None = None,
    fingerprint: str | None = None,
) -> IngestEventResult:
    if sealed is None:
        try:
            sealed = event.envelope.to_sealed()
        except CryptoError as exc:
            raise ValueError(str(exc)) from exc

    stored_event_type = event_type if event_type is not None else event.event_type
    if ciphertext_bytes is None:
        ciphertext_bytes = len(b64decode(sealed.ciphertext))
    if fingerprint is None:
        fingerprint = _event_fingerprint(
            event,
            workflow_id=workflow.id,
            event_type=stored_event_type,
            ciphertext_bytes=ciphertext_bytes,
        )

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO telemetry_events (
                tenant_id, submitted_by, client_event_id, occurred_at,
                algo, key_id, ratchet_header, nonce, ciphertext, ciphertext_sha256,
                ciphertext_bytes, ingest_fingerprint,
                content_type, event_type, schema_version, workflow_id, metadata,
                created_at
            )
            VALUES (
                $1::uuid, $2::uuid, $3, $4,
                $5, $6, $7, $8, $9, $10,
                $11, $12,
                $13, $14, $15, $16, $17::jsonb,
                GREATEST(
                    clock_timestamp(),
                    COALESCE(
                        (
                            SELECT MAX(existing.created_at) + INTERVAL '1 microsecond'
                            FROM telemetry_events AS existing
                            WHERE existing.tenant_id = $1::uuid
                              AND existing.workflow_id = $16
                        ),
                        clock_timestamp()
                    )
                )
            )
            ON CONFLICT (tenant_id, client_event_id) DO NOTHING
            RETURNING id, tenant_id, client_event_id, created_at
            """,
            str(event.tenant_id),
            # Human auth.users id only — services use audit actor_id (svc:…); avoid FK break.
            user.user_id if user.is_user else None,
            event.client_event_id,
            event.occurred_at,
            sealed.algo,
            sealed.key_id,
            sealed.ratchet_header,
            sealed.nonce,
            sealed.ciphertext,
            sealed.ciphertext_sha256,
            ciphertext_bytes,
            fingerprint,
            event.content_type,
            stored_event_type,
            event.schema_version,
            workflow.id,
            json.dumps(event.metadata),
        )
    except asyncpg.UniqueViolationError as exc:
        # sql/013: (tenant_id, key_id, nonce) — AES-GCM nonce must never repeat.
        raise ValueError("nonce reuse rejected for this key_id") from exc
    if row is not None:
        return IngestEventResult(
            id=row["id"],
            tenant_id=row["tenant_id"],
            client_event_id=row["client_event_id"],
            created_at=row["created_at"],
            duplicate=False,
            workflow_id=workflow.id,
        )

    existing = await pool.fetchrow(
        """
        SELECT id, tenant_id, client_event_id, created_at, occurred_at,
               algo, key_id, ratchet_header, nonce, ciphertext_sha256,
               ciphertext_bytes, ingest_fingerprint, content_type, event_type,
               schema_version, workflow_id, metadata
        FROM telemetry_events
        WHERE tenant_id = $1::uuid AND client_event_id = $2
        """,
        str(event.tenant_id),
        event.client_event_id,
    )
    if existing is None:
        raise RuntimeError("ingest conflict without existing row")
    existing_meta = existing["metadata"] or {}
    if isinstance(existing_meta, str):
        existing_meta = json.loads(existing_meta)
    existing_fingerprint = existing["ingest_fingerprint"]
    if not existing_fingerprint:
        existing_fingerprint = _fingerprint_values(
            occurred_at=existing["occurred_at"],
            encryption_mode="e2ee",
            algo=existing["algo"],
            key_id=existing["key_id"],
            ratchet_header=existing["ratchet_header"],
            nonce=existing["nonce"],
            ciphertext_sha256=existing["ciphertext_sha256"],
            ciphertext_bytes=int(existing["ciphertext_bytes"] or 0),
            content_type=existing["content_type"],
            event_type=existing["event_type"],
            schema_version=int(existing["schema_version"]),
            workflow_id=existing["workflow_id"] or workflow.id,
            metadata=existing_meta,
        )
    if existing_fingerprint != fingerprint:
        raise IngestConflictError(
            "client_event_id already used with different routing or encryption metadata"
        )
    if not existing["ingest_fingerprint"]:
        await pool.execute(
            """
            UPDATE telemetry_events
            SET ingest_fingerprint = $2, ciphertext_bytes = $3
            WHERE id = $1::uuid AND ingest_fingerprint IS NULL
            """,
            str(existing["id"]),
            fingerprint,
            ciphertext_bytes,
        )
    return IngestEventResult(
        id=existing["id"],
        tenant_id=existing["tenant_id"],
        client_event_id=existing["client_event_id"],
        created_at=existing["created_at"],
        duplicate=True,
        workflow_id=existing.get("workflow_id") or workflow.id,
    )


# --- Embedding vectors (optional sealed context columns) ---
async def ingest_embedding(
    *,
    pool: asyncpg.Pool,
    user: AuthUser,
    body: EmbeddingIngestRequest,
) -> dict[str, Any]:
    await tenant_svc.ensure_secure_schema(pool)
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=body.tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"ingest:write"}),
    )
    if body.telemetry_event_id is not None:
        event_exists = await pool.fetchval(
            """
            SELECT EXISTS (
              SELECT 1 FROM telemetry_events
              WHERE id = $1::uuid AND tenant_id = $2::uuid
            )
            """,
            str(body.telemetry_event_id),
            str(body.tenant_id),
        )
        if not event_exists:
            raise ValueError("telemetry_event_id does not belong to this tenant")

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


# --- List metadata only (omit ciphertext / nonce / ratchet_header) ---
async def list_recent_events(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    limit: int = 20,
) -> list[dict[str, Any]]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"ingest:read", "ingest:write"}),
    )
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, client_event_id, created_at, occurred_at,
               algo, key_id, content_type, event_type, schema_version, workflow_id,
               ciphertext_sha256, ciphertext_bytes, ingest_fingerprint, metadata
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
                "event_type": r["event_type"],
                "schema_version": r["schema_version"],
                "workflow_id": r["workflow_id"],
                "ciphertext_sha256": r["ciphertext_sha256"],
                "ciphertext_bytes": r["ciphertext_bytes"],
                "ingest_fingerprint": r["ingest_fingerprint"],
                "metadata": meta,
            }
        )
    return out


# --- List stream results for any SaaS consumer (scores only; no ciphertext) ---
async def list_stream_results(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    limit: int = 20,
    anomalies_only: bool = False,
    workflow_id: str | None = None,
    since: datetime | None = None,
    after_id: UUID | None = None,
) -> list[dict[str, Any]]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"ingest:read", "projections:read"}),
    )
    clauses = ["tenant_id = $1::uuid"]
    args: list[Any] = [str(tenant_id)]
    if anomalies_only:
        clauses.append("is_anomaly = TRUE")
    canon_wf = canonical_workflow_id(workflow_id)
    if canon_wf:
        args.append(canon_wf)
        clauses.append(f"workflow_id = ${len(args)}")
    if since is not None:
        args.append(since)
        clauses.append(f"created_at > ${len(args)}")
    if after_id is not None:
        args.append(str(after_id))
        clauses.append(
            f"(created_at, id) > ("
            f"(SELECT created_at FROM stream_results"
            f" WHERE id = ${len(args)}::uuid AND tenant_id = $1::uuid), "
            f"${len(args)}::uuid)"
        )
    order = "ASC" if (since is not None or after_id is not None) else "DESC"
    args.append(limit)
    limit_ph = f"${len(args)}"
    where = " AND ".join(clauses)
    rows = await pool.fetch(
        f"""
        SELECT id::text, tenant_id::text, telemetry_event_id::text,
               source_event_id::text,
               created_at, kind, engine, score, is_anomaly, features, metadata,
               workflow_id, projection_name, projection_version,
               projection_result_key
        FROM stream_results
        WHERE {where}
        ORDER BY created_at {order}, id {order}
        LIMIT {limit_ph}
        """,
        *args,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        features = r["features"]
        meta = r["metadata"]
        if isinstance(features, str):
            features = json.loads(features)
        if isinstance(meta, str):
            meta = json.loads(meta)
        out.append(
            {
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "telemetry_event_id": r["telemetry_event_id"],
                "source_event_id": r["source_event_id"],
                "created_at": r["created_at"].isoformat(),
                "kind": r["kind"],
                "engine": r["engine"],
                "score": r["score"],
                "is_anomaly": r["is_anomaly"],
                "features": features,
                "metadata": meta,
                "workflow_id": r["workflow_id"],
                "projection_name": r["projection_name"],
                "projection_version": r["projection_version"],
                "projection_result_key": r["projection_result_key"],
            }
        )
    return out
