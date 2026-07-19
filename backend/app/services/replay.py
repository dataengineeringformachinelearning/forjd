"""Event replay + projection DLQ (checkpointed reliability, E2EE-safe).

Replays sealed-event *metadata* through configured workflows. Ciphertext is
never loaded into Pathway. Failures land in projection_dlq for retry.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.pipelines.projections import run_project_flow
from app.services import projections as proj_svc
from app.services import tenants as tenant_svc
from app.workflows.registry import canonical_workflow_id, resolve_workflow

logger = logging.getLogger("forjd.replay")


# --- Load metadata for a time / id range (no ciphertext bodies) ---
async def fetch_meta_range(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    from_time: datetime | None,
    to_time: datetime | None,
    from_event_id: UUID | None,
    workflow_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses = ["tenant_id = $1::uuid"]
    args: list[Any] = [str(tenant_id)]
    canon_wf = canonical_workflow_id(workflow_id)
    if canon_wf:
        args.append(canon_wf)
        clauses.append(f"workflow_id = ${len(args)}")
    if from_time is not None:
        args.append(from_time)
        clauses.append(f"created_at >= ${len(args)}")
    if to_time is not None:
        args.append(to_time)
        clauses.append(f"created_at <= ${len(args)}")
    if from_event_id is not None:
        args.append(str(from_event_id))
        clauses.append(
            f"created_at >= (SELECT created_at FROM telemetry_events WHERE id = ${len(args)}::uuid)"
        )
    args.append(limit)
    rows = await pool.fetch(
        f"""
        SELECT id::text, tenant_id::text, key_id, content_type, event_type,
               workflow_id, created_at, length(ciphertext) AS cipher_len
        FROM telemetry_events
        WHERE {" AND ".join(clauses)}
        ORDER BY created_at ASC, id ASC
        LIMIT ${len(args)}
        """,
        *args,
    )
    return [
        {
            "event_id": r["id"],
            "tenant_id": r["tenant_id"],
            "key_id": r["key_id"],
            "cipher_len": int(r["cipher_len"] or 0),
            "content_type": r["content_type"] or "application/forjd-event+v1",
            "event_type": r["event_type"] or "",
            "workflow_id": r["workflow_id"] or "",
            "created_at": r["created_at"],
        }
        for r in rows
    ]


# --- DLQ helpers ---
async def enqueue_dlq(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    source_event_id: str | None,
    workflow_id: str | None,
    projection_name: str,
    error: str,
    payload_meta: dict[str, Any],
) -> None:
    await pool.execute(
        """
        INSERT INTO projection_dlq (
            tenant_id, source_event_id, workflow_id, projection_name,
            error, payload_meta, attempts
        )
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6::jsonb, 1)
        """,
        tenant_id,
        source_event_id,
        workflow_id,
        projection_name,
        error[:4000],
        json.dumps(payload_meta),
    )


async def list_dlq(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    limit: int = 50,
    open_only: bool = True,
) -> list[dict[str, Any]]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"replay:read"}),
    )
    clause = "AND resolved_at IS NULL" if open_only else ""
    rows = await pool.fetch(
        f"""
        SELECT id::text, tenant_id::text, source_event_id::text, workflow_id,
               projection_name, error, payload_meta, attempts,
               created_at, resolved_at
        FROM projection_dlq
        WHERE tenant_id = $1::uuid
        {clause}
        ORDER BY created_at DESC
        LIMIT $2
        """,
        str(tenant_id),
        limit,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        meta = r["payload_meta"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        out.append(
            {
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "source_event_id": r["source_event_id"],
                "workflow_id": r["workflow_id"],
                "projection_name": r["projection_name"],
                "error": r["error"],
                "payload_meta": meta,
                "attempts": r["attempts"],
                "created_at": r["created_at"].isoformat(),
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
            }
        )
    return out


# --- Replay range through configured workflow ---
async def replay_events(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    from_event_id: UUID | None = None,
    workflow_id: str | None = None,
    limit: int = 200,
    dry_run: bool = False,
) -> dict[str, Any]:
    await tenant_svc.ensure_secure_schema(pool)
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin"}),
        required_scopes=frozenset({"replay:write"}),
    )
    limit = max(1, min(limit, 1000))
    meta = await fetch_meta_range(
        pool,
        tenant_id=tenant_id,
        from_time=from_time,
        to_time=to_time,
        from_event_id=from_event_id,
        workflow_id=workflow_id,
        limit=limit,
    )
    if not meta:
        return {"ok": True, "matched": 0, "written": 0, "dry_run": dry_run}

    content_type = meta[0]["content_type"]
    wf = resolve_workflow(
        content_type=content_type,
        event_type=meta[0].get("event_type") or None,
        workflow_id=workflow_id or meta[0].get("workflow_id") or None,
    )
    if dry_run:
        return {
            "ok": True,
            "matched": len(meta),
            "written": 0,
            "dry_run": True,
            "workflow_id": wf.id,
            "projection_name": wf.pipeline.projection_name,
            "sample_event_ids": [m["event_id"] for m in meta[:10]],
        }

    try:
        flow = run_project_flow(
            tenant_id=str(tenant_id),
            events=meta,
            content_type=content_type,
            event_type=meta[0].get("event_type") or None,
            workflow_id=wf.id,
        )
        written = await proj_svc.upsert_stream_results(pool, flow.get("stream_results") or [])
        return {
            "ok": True,
            "matched": len(meta),
            "written": written,
            "dry_run": False,
            "workflow_id": wf.id,
            "projection_name": wf.pipeline.projection_name,
            "anomaly_count": (flow.get("pathway") or {}).get("anomaly_count", 0),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("replay failed")
        for m in meta[:20]:
            await enqueue_dlq(
                pool,
                tenant_id=str(tenant_id),
                source_event_id=m["event_id"],
                workflow_id=wf.id,
                projection_name=wf.pipeline.projection_name,
                error=str(exc),
                payload_meta={
                    "content_type": m.get("content_type"),
                    "event_type": m.get("event_type"),
                    "cipher_len": m.get("cipher_len"),
                },
            )
        return {
            "ok": False,
            "matched": len(meta),
            "written": 0,
            "error": str(exc),
            "dlq_enqueued": min(len(meta), 20),
        }


# --- Retry one DLQ row ---
async def retry_dlq_item(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    dlq_id: UUID,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin"}),
        required_scopes=frozenset({"replay:write"}),
    )
    row = await pool.fetchrow(
        """
        SELECT id, source_event_id::text, workflow_id, projection_name, payload_meta
        FROM projection_dlq
        WHERE id = $1::uuid AND tenant_id = $2::uuid AND resolved_at IS NULL
        """,
        str(dlq_id),
        str(tenant_id),
    )
    if row is None:
        raise ValueError("dlq item not found or already resolved")

    source_id = row["source_event_id"]
    if not source_id:
        raise ValueError("dlq item has no source_event_id")

    result = await replay_events(
        pool,
        user=user,
        tenant_id=tenant_id,
        from_event_id=UUID(source_id),
        workflow_id=row["workflow_id"],
        limit=1,
        dry_run=False,
    )
    if result.get("ok"):
        await pool.execute(
            """
            UPDATE projection_dlq
            SET resolved_at = NOW(), attempts = attempts + 1
            WHERE id = $1::uuid
            """,
            str(dlq_id),
        )
    else:
        await pool.execute(
            "UPDATE projection_dlq SET attempts = attempts + 1 WHERE id = $1::uuid",
            str(dlq_id),
        )
    return {"ok": bool(result.get("ok")), "dlq_id": str(dlq_id), "replay": result}
