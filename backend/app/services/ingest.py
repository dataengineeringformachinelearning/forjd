"""Universal E2EE event ingestion — store ciphertext only, run configured workflows.

Ingest path guarantees:
  • Caller presents a verified principal (`get_current_user`): enterprise user JWT
    or tenant-scoped service token (subprocessor / M2M, e.g. DEML).
  • Tenant isolation checked before any write (`require_tenant_access`).
  • Envelope fields are validated but **never decrypted**.
  • Workflow YAML/JSON selects processor + thresholds (not product forks).
  • Prefect + Pathway receive metadata only; results land in `stream_results`.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
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
from app.services import audit
from app.services import projections as proj_svc
from app.services import sessions as session_svc
from app.services import tenants as tenant_svc
from app.workflows.models import WorkflowDefinition
from app.workflows.registry import resolve_workflow

logger = logging.getLogger("forjd.ingest")


# --- Helpers ---
def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.8g}" for x in embedding) + "]"


def _validate_encryption(event: IngestEventRequest, workflow: WorkflowDefinition) -> None:
    """Fail closed if client encryption is outside the workflow policy."""
    mode = event.encryption.mode
    algo = event.encryption.algo
    if mode not in workflow.encryption.modes:
        raise ValueError(
            f"encryption.mode={mode!r} not allowed for workflow {workflow.id!r}"
        )
    if algo not in workflow.encryption.algos:
        raise ValueError(
            f"encryption.algo={algo!r} not allowed for workflow {workflow.id!r}"
        )
    if event.envelope.algo != algo:
        raise ValueError("envelope.algo must match encryption.algo")


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

    results: list[IngestEventResult] = []
    # Group metadata by workflow so mixed batches still get correct processors.
    by_workflow: dict[str, list[dict[str, Any]]] = defaultdict(list)
    workflow_meta: dict[str, tuple[str, str | None]] = {}

    for event in batch.events:
        workflow = resolve_workflow(
            content_type=event.content_type,
            event_type=event.event_type,
            workflow_id=event.workflow_id,
        )
        _validate_encryption(event, workflow)
        # Zero-trust: key_id must be a registered crypto session (prod).
        await session_svc.require_active_session(
            pool, tenant_id=event.tenant_id, key_id=event.envelope.key_id
        )
        result = await _insert_event(pool, user=user, event=event, workflow=workflow)
        results.append(result)

        try:
            sealed = event.envelope.to_sealed()
            cipher_len = len(sealed.ciphertext)
        except CryptoError:
            cipher_len = 0

        # Metadata only — never pass ciphertext into Prefect / Pathway.
        by_workflow[workflow.id].append(
            {
                "event_id": str(result.id),
                "tenant_id": str(event.tenant_id),
                "key_id": event.envelope.key_id,
                "cipher_len": cipher_len,
                "content_type": event.content_type,
                "event_type": event.event_type or "",
                "workflow_id": workflow.id,
            }
        )
        workflow_meta[workflow.id] = (event.content_type, event.event_type)

    prefect_runs: list[dict[str, Any]] = []
    pathway_summary: dict[str, Any] = {
        "ok": True,
        "count": 0,
        "tenants": 0,
        "by_tenant": {},
        "anomaly_count": 0,
        "workflows": [],
    }
    persisted = 0

    try:
        for wf_id, meta_rows in by_workflow.items():
            ct, et = workflow_meta[wf_id]
            run = run_ingest_flow(
                user_id=user.actor_id,
                tenant_ids=[str(t) for t in tenant_ids],
                accepted=len(meta_rows),
                event_ids=[str(r["event_id"]) for r in meta_rows],
                events=meta_rows,
                content_type=ct,
                event_type=et,
                workflow_id=wf_id,
            )
            prefect_runs.append(
                {k: v for k, v in run.items() if k not in {"pathway", "stream_results"}}
            )
            pathway = run.get("pathway") or {}
            pathway_summary["count"] += int(pathway.get("count") or 0)
            pathway_summary["anomaly_count"] += int(pathway.get("anomaly_count") or 0)
            pathway_summary["ok"] = pathway_summary["ok"] and bool(pathway.get("ok"))
            if pathway.get("engine"):
                pathway_summary["engine"] = pathway.get("engine")
            for tid, stats in (pathway.get("by_tenant") or {}).items():
                slot = pathway_summary["by_tenant"].setdefault(
                    tid, {"count": 0, "bytes": 0, "max_cipher_len": 0}
                )
                slot["count"] += int(stats.get("count") or 0)
                slot["bytes"] += int(stats.get("bytes") or 0)
                slot["max_cipher_len"] = max(
                    slot["max_cipher_len"], int(stats.get("max_cipher_len") or 0)
                )
            pathway_summary["workflows"].append(wf_id)
            persisted += await proj_svc.upsert_stream_results(
                pool, run.get("stream_results") or []
            )
            # Keep durable projection watermarks aligned with live ingest path.
            await proj_svc.advance_checkpoint_from_meta(
                pool, meta_rows=meta_rows, workflow_id=wf_id
            )
        pathway_summary["tenants"] = len(pathway_summary["by_tenant"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest prefect/pathway failed")
        prefect_runs.append({"ok": False, "error": str(exc)})
        pathway_summary["ok"] = False
        pathway_summary["error"] = str(exc)

    # Metadata-only audit (never ciphertext / keys).
    for tid in tenant_ids:
        await audit.record(
            pool,
            action=audit.ACTION_INGEST_BATCH,
            actor_user_id=user.actor_id,
            tenant_id=tid,
            resource_type="ingest_batch",
            details={
                "accepted": len(results),
                "workflows": list(by_workflow.keys()),
                "anomaly_count": pathway_summary.get("anomaly_count", 0),
                "principal_kind": user.kind.value,
                "subprocessor": user.subprocessor or "",
            },
        )

    return {
        "ok": True,
        "accepted": len(results),
        "results": results,
        "pathway": pathway_summary,
        "stream_results_written": persisted,
        "prefect": prefect_runs[0] if len(prefect_runs) == 1 else {"runs": prefect_runs},
    }


# --- Single-event persist (idempotent; never decrypts) ---
async def _insert_event(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    event: IngestEventRequest,
    workflow: WorkflowDefinition,
) -> IngestEventResult:
    try:
        sealed = event.envelope.to_sealed()
    except CryptoError as exc:
        raise ValueError(str(exc)) from exc

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO telemetry_events (
                tenant_id, submitted_by, client_event_id, occurred_at,
                algo, key_id, ratchet_header, nonce, ciphertext, ciphertext_sha256,
                content_type, event_type, schema_version, workflow_id, metadata
            )
            VALUES (
                $1::uuid, $2::uuid, $3, $4,
                $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15::jsonb
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
            event.content_type,
            event.event_type,
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
        SELECT id, tenant_id, client_event_id, created_at, ciphertext_sha256, workflow_id
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
                "event_type": r["event_type"],
                "schema_version": r["schema_version"],
                "workflow_id": r["workflow_id"],
                "ciphertext_sha256": r["ciphertext_sha256"],
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
    if workflow_id:
        args.append(workflow_id)
        clauses.append(f"workflow_id = ${len(args)}")
    args.append(limit)
    limit_ph = f"${len(args)}"
    where = " AND ".join(clauses)
    rows = await pool.fetch(
        f"""
        SELECT id::text, tenant_id::text, telemetry_event_id::text,
               created_at, kind, engine, score, is_anomaly, features, metadata,
               workflow_id
        FROM stream_results
        WHERE {where}
        ORDER BY created_at DESC
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
                "created_at": r["created_at"].isoformat(),
                "kind": r["kind"],
                "engine": r["engine"],
                "score": r["score"],
                "is_anomaly": r["is_anomaly"],
                "features": features,
                "metadata": meta,
                "workflow_id": r["workflow_id"],
            }
        )
    return out
