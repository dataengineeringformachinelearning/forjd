"""Event replay + projection DLQ (checkpointed reliability, E2EE-safe).

Replays sealed-event *metadata* through configured workflows. Ciphertext is
never loaded into Pathway. Failures land in projection_dlq for retry.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from app.core.auth import AuthUser
from app.pipelines.projections import run_project_flow
from app.services import projections as proj_svc
from app.services import tenants as tenant_svc
from app.workflows.registry import canonical_workflow_id, resolve_workflow

logger = logging.getLogger("forjd.replay")


def _meta_from_row(row: Any) -> dict[str, Any]:
    return {
        "event_id": row["id"],
        "tenant_id": row["tenant_id"],
        "key_id": row["key_id"],
        "cipher_len": int(row["cipher_len"] or 0),
        "content_type": row["content_type"] or "application/forjd-event+v1",
        "event_type": row["event_type"] or "",
        "workflow_id": row["workflow_id"] or "",
        "created_at": row["created_at"],
    }


def _retry_backoff_seconds(attempts: int) -> int:
    """Bounded exponential retry delay (30 seconds through one hour)."""
    return min(3600, 30 * (2 ** max(0, min(attempts - 1, 7))))


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
            f"(created_at, id) >= (SELECT created_at, id FROM telemetry_events"
            f" WHERE id = ${len(args)}::uuid AND tenant_id = $1::uuid)"
        )
    args.append(limit)
    rows = await pool.fetch(
        f"""
        SELECT id::text, tenant_id::text, key_id, content_type, event_type,
               workflow_id, created_at, ciphertext_bytes AS cipher_len
        FROM telemetry_events
        WHERE {" AND ".join(clauses)}
        ORDER BY created_at ASC, id ASC
        LIMIT ${len(args)}
        """,
        *args,
    )
    return [_meta_from_row(row) for row in rows]


async def fetch_meta_event(
    pool: asyncpg.Pool | asyncpg.Connection,
    *,
    tenant_id: UUID,
    event_id: UUID,
) -> dict[str, Any] | None:
    """Load exactly one tenant-bound event for DLQ retry."""
    row = await pool.fetchrow(
        """
        SELECT id::text, tenant_id::text, key_id, content_type, event_type,
               workflow_id, created_at, ciphertext_bytes AS cipher_len
        FROM telemetry_events
        WHERE tenant_id = $1::uuid AND id = $2::uuid
        """,
        str(tenant_id),
        str(event_id),
    )
    return _meta_from_row(row) if row else None


# --- DLQ helpers ---
async def enqueue_dlq(
    pool: asyncpg.Pool | asyncpg.Connection,
    *,
    tenant_id: str,
    source_event_id: str | None,
    workflow_id: str | None,
    projection_name: str,
    projection_version: int,
    error: str,
    payload_meta: dict[str, Any],
) -> str:
    return await proj_svc.enqueue_projection_dlq(
        pool,
        tenant_id=tenant_id,
        source_event_id=source_event_id,
        workflow_id=workflow_id,
        projection_name=projection_name,
        projection_version=projection_version,
        error=error,
        payload_meta=payload_meta,
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
               projection_name, projection_version, error, error_class,
               payload_meta, attempts,
               max_attempts, next_attempt_at, last_attempt_at, locked_at,
               locked_by, lease_expires_at, created_at, updated_at, resolved_at
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
                "projection_version": r["projection_version"],
                "error": r["error"],
                "error_class": r["error_class"],
                "payload_meta": meta,
                "attempts": r["attempts"],
                "max_attempts": r["max_attempts"],
                "next_attempt_at": r["next_attempt_at"].isoformat(),
                "last_attempt_at": (
                    r["last_attempt_at"].isoformat() if r["last_attempt_at"] else None
                ),
                "locked_at": r["locked_at"].isoformat() if r["locked_at"] else None,
                "locked_by": r["locked_by"],
                "lease_expires_at": (
                    r["lease_expires_at"].isoformat() if r["lease_expires_at"] else None
                ),
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
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

    groups: dict[str, dict[str, Any]] = {}
    for item in meta:
        wf = resolve_workflow(
            content_type=item["content_type"],
            event_type=item.get("event_type") or None,
            workflow_id=workflow_id or item.get("workflow_id") or None,
        )
        slot = groups.setdefault(wf.id, {"workflow": wf, "events": []})
        slot["events"].append(item)

    if dry_run:
        return {
            "ok": True,
            "matched": len(meta),
            "written": 0,
            "dry_run": True,
            "workflows": [
                {
                    "workflow_id": item["workflow"].id,
                    "projection_name": item["workflow"].pipeline.projection_name,
                    "events": len(item["events"]),
                }
                for item in groups.values()
            ],
            "sample_event_ids": [m["event_id"] for m in meta[:10]],
        }

    written = 0
    anomaly_count = 0
    dlq_enqueued = 0
    errors: list[dict[str, str]] = []
    for group in groups.values():
        wf = group["workflow"]
        events = group["events"]
        try:
            flow = await asyncio.to_thread(
                run_project_flow,
                tenant_id=str(tenant_id),
                events=events,
                content_type=events[0]["content_type"],
                event_type=events[0].get("event_type") or None,
                workflow_id=wf.id,
            )
            pathway = flow.get("pathway") or {}
            if not pathway.get("ok"):
                raise RuntimeError(
                    str(pathway.get("error") or "processor reported an unsuccessful result")
                )
            event_ids = {str(item["event_id"]) for item in events}
            written += await proj_svc.upsert_stream_results(
                pool,
                flow.get("stream_results") or [],
                projection_version=wf.pipeline.projection.version,
                aggregate_event_ids=sorted(event_ids),
                expected_tenant_ids={str(tenant_id)},
                expected_event_ids=event_ids,
            )
            anomaly_count += int(pathway.get("anomaly_count") or 0)
        except Exception as exc:  # noqa: BLE001
            logger.exception("replay failed workflow=%s", wf.id)
            errors.append({"workflow_id": wf.id, "error": str(exc)})
            for item in events:
                await enqueue_dlq(
                    pool,
                    tenant_id=str(tenant_id),
                    source_event_id=item["event_id"],
                    workflow_id=wf.id,
                    projection_name=wf.pipeline.projection_name,
                    projection_version=wf.pipeline.projection.version,
                    error=str(exc),
                    payload_meta=item,
                )
                dlq_enqueued += 1

    return {
        "ok": not errors,
        "matched": len(meta),
        "written": written,
        "dry_run": False,
        "anomaly_count": anomaly_count,
        "dlq_enqueued": dlq_enqueued,
        "errors": errors,
        "workflows": sorted(groups),
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
    lease_owner = f"{user.actor_id}:{uuid4()}"
    row = await pool.fetchrow(
        """
        UPDATE projection_dlq
        SET attempts = attempts + 1,
            last_attempt_at = NOW(),
            locked_at = NOW(),
            locked_by = $3,
            lease_expires_at = NOW() + INTERVAL '5 minutes',
            updated_at = NOW()
        WHERE id = $1::uuid
          AND tenant_id = $2::uuid
          AND resolved_at IS NULL
          AND attempts < max_attempts
          AND next_attempt_at <= NOW()
          AND (lease_expires_at IS NULL OR lease_expires_at <= NOW())
        RETURNING id, source_event_id::text, workflow_id, projection_name,
                  projection_version, payload_meta, attempts, max_attempts
        """,
        str(dlq_id),
        str(tenant_id),
        lease_owner,
    )
    if row is None:
        raise ValueError("dlq item is missing, resolved, exhausted, leased, or not retry-ready")

    source_id = row["source_event_id"]
    if not source_id:
        raise ValueError("dlq item has no source_event_id")

    try:
        meta = await fetch_meta_event(
            pool,
            tenant_id=tenant_id,
            event_id=UUID(source_id),
        )
        if meta is None:
            raise RuntimeError("source event no longer exists in this tenant")
        wf = resolve_workflow(
            content_type=meta["content_type"],
            event_type=meta.get("event_type") or None,
            workflow_id=row["workflow_id"] or meta.get("workflow_id") or None,
        )
        queued_projection_version = int(row["projection_version"])
        queued_projection_name = str(row["projection_name"])
        if (
            wf.pipeline.projection_name != queued_projection_name
            or wf.pipeline.projection.version != queued_projection_version
        ):
            raise RuntimeError(
                "DLQ projection contract no longer matches the active workflow; "
                "restore that projection name/version or perform an explicit range replay"
            )
        flow = await asyncio.to_thread(
            run_project_flow,
            tenant_id=str(tenant_id),
            events=[meta],
            content_type=meta["content_type"],
            event_type=meta.get("event_type") or None,
            workflow_id=wf.id,
        )
        pathway = flow.get("pathway") or {}
        if not pathway.get("ok"):
            raise RuntimeError(
                str(pathway.get("error") or "processor reported an unsuccessful result")
            )
        written = await proj_svc.upsert_stream_results(
            pool,
            flow.get("stream_results") or [],
            projection_version=queued_projection_version,
            aggregate_event_ids=[source_id],
            expected_tenant_ids={str(tenant_id)},
            expected_event_ids={source_id},
        )
        completion = await pool.execute(
            """
            UPDATE projection_dlq
            SET resolved_at = NOW(), locked_at = NULL, locked_by = NULL,
                lease_expires_at = NULL, updated_at = NOW()
            WHERE id = $1::uuid AND tenant_id = $2::uuid AND locked_by = $3
            """,
            str(dlq_id),
            str(tenant_id),
            lease_owner,
        )
        if str(completion) != "UPDATE 1":
            raise RuntimeError("DLQ retry lease was lost before completion")
        return {
            "ok": True,
            "dlq_id": str(dlq_id),
            "source_event_id": source_id,
            "written": written,
            "attempts": row["attempts"],
        }
    except Exception as exc:  # noqa: BLE001
        delay = _retry_backoff_seconds(int(row["attempts"]))
        await pool.execute(
            """
            UPDATE projection_dlq
            SET error = $4,
                error_class = 'retry_error',
                next_attempt_at = NOW() + ($5 * INTERVAL '1 second'),
                locked_at = NULL,
                locked_by = NULL,
                lease_expires_at = NULL,
                updated_at = NOW()
            WHERE id = $1::uuid AND tenant_id = $2::uuid AND locked_by = $3
            """,
            str(dlq_id),
            str(tenant_id),
            lease_owner,
            str(exc)[:4000],
            delay,
        )
        return {
            "ok": False,
            "dlq_id": str(dlq_id),
            "source_event_id": source_id,
            "attempts": row["attempts"],
            "max_attempts": row["max_attempts"],
            "retry_after_seconds": delay,
            "error": str(exc),
        }
