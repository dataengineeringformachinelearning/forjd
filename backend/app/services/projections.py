"""Durable live projections — checkpointed reprocess of sealed metadata.

Idempotent upserts + watermarks; no plaintext. Ciphertext stays in
telemetry_events; processors see sizes/routing only.

Subprocessor consumers (partner SaaS backends)
----------------------------------------------
1. Mint a tenant-bound ``fjsvc_…`` token (human JWT → POST /service-accounts).
2. Poll ``GET /api/v1/projections?tenant_id=&since=`` (or Realtime on
   ``stream_results`` / ``projection_feed``).
3. Optionally ``POST /api/v1/projections/run`` with ``projections:run`` to
   advance watermarks after backfill.
Partner end-user tokens are never sent here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.pipelines.projections import run_project_flow
from app.services import tenants as tenant_svc
from app.workflows.registry import canonical_workflow_id, resolve_workflow

logger = logging.getLogger("forjd.projections")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def projection_lease_name(
    *,
    tenant_id: UUID | str,
    projection_name: str,
    workflow_id: str,
) -> str:
    """Shared DB lock identity for acceptance and projection ordering."""
    return f"forjd:projection:{tenant_id}:{projection_name}:{workflow_id}"


def projection_acceptance_fence_name(
    *,
    tenant_id: UUID | str,
    projection_name: str,
    workflow_id: str,
) -> str:
    """Short snapshot fence shared by canonical ingest and the projector."""
    return (
        projection_lease_name(
            tenant_id=tenant_id,
            projection_name=projection_name,
            workflow_id=workflow_id,
        )
        + ":acceptance"
    )


def _projection_result_key(
    row: dict[str, Any],
    *,
    projection_name: str,
    projection_version: int,
    aggregate_event_ids: list[str] | None = None,
) -> str:
    """Stable identity for one source detector or an exact aggregate input set."""
    features = dict(row.get("features") or {})
    metadata = dict(row.get("metadata") or {})
    source_id = row.get("source_event_id") or row.get("telemetry_event_id")
    workflow_id = str(row.get("workflow_id") or metadata.get("workflow_id") or "")
    if source_id:
        identity: dict[str, Any] = {
            "type": "source",
            "source_event_id": str(source_id),
            "detector": str(
                features.get("detector")
                or metadata.get("detector")
                or row.get("kind")
                or "transform"
            ),
            "rule_id": str(
                features.get("rule_id") or metadata.get("rule_id") or row.get("rule_id") or ""
            ),
        }
    else:
        event_ids = sorted({str(event_id) for event_id in (aggregate_event_ids or [])})
        identity = {
            "type": "aggregate",
            "event_ids": event_ids,
            "kind": str(row.get("kind") or "rollup"),
        }
        if not event_ids:
            # Backward-compatible deterministic fallback for callers that do not
            # yet supply the input event ids.
            identity["features"] = features
            identity["metadata"] = metadata
    payload = {
        "projection_name": projection_name,
        "projection_version": projection_version,
        "workflow_id": workflow_id,
        "identity": identity,
    }
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _dlq_dedupe_key(
    *,
    source_event_id: str | None,
    workflow_id: str | None,
    projection_name: str,
    projection_version: int,
) -> str:
    body = {
        "source_event_id": source_event_id or "",
        "workflow_id": workflow_id or "",
        "projection_name": projection_name,
        "projection_version": projection_version,
    }
    return hashlib.sha256(_json_dumps(body).encode("utf-8")).hexdigest()


async def enqueue_projection_dlq(
    pool: asyncpg.Pool | asyncpg.Connection,
    *,
    tenant_id: str,
    source_event_id: str | None,
    workflow_id: str | None,
    projection_name: str,
    projection_version: int,
    error: str,
    payload_meta: dict[str, Any],
    error_class: str = "processing_error",
) -> str:
    """Upsert one open DLQ item per event/projection version."""
    safe_meta = {
        key: payload_meta.get(key)
        for key in (
            "event_id",
            "content_type",
            "event_type",
            "cipher_len",
            "workflow_id",
            "created_at",
        )
        if payload_meta.get(key) is not None
    }
    row = await pool.fetchrow(
        """
        INSERT INTO projection_dlq (
            tenant_id, source_event_id, workflow_id, projection_name, projection_version,
            error, error_class, payload_meta, attempts, dedupe_key,
            next_attempt_at, updated_at
        )
        VALUES (
            $1::uuid, $2::uuid, $3, $4, $5,
            $6, $7, $8::jsonb, 0, $9, NOW(), NOW()
        )
        ON CONFLICT (tenant_id, dedupe_key) WHERE resolved_at IS NULL
        DO UPDATE SET
            error = EXCLUDED.error,
            error_class = EXCLUDED.error_class,
            payload_meta = EXCLUDED.payload_meta,
            next_attempt_at = LEAST(projection_dlq.next_attempt_at, NOW()),
            updated_at = NOW()
        RETURNING id::text
        """,
        tenant_id,
        source_event_id,
        workflow_id,
        projection_name,
        projection_version,
        error[:4000],
        error_class[:128],
        _json_dumps(safe_meta),
        _dlq_dedupe_key(
            source_event_id=source_event_id,
            workflow_id=workflow_id,
            projection_name=projection_name,
            projection_version=projection_version,
        ),
    )
    return str(row["id"])


async def resolve_projection_dlq_for_events(
    pool: asyncpg.Pool | asyncpg.Connection,
    *,
    tenant_id: str,
    source_event_ids: list[str],
    workflow_id: str,
    projection_name: str,
    projection_version: int,
) -> int:
    """Close matching, unleased replay rows after their live projection succeeds."""
    if not source_event_ids:
        return 0
    status = await pool.execute(
        """
        UPDATE projection_dlq
        SET resolved_at = NOW(), locked_at = NULL, locked_by = NULL,
            lease_expires_at = NULL, updated_at = NOW()
        WHERE tenant_id = $1::uuid
          AND source_event_id = ANY($2::uuid[])
          AND workflow_id = $3
          AND projection_name = $4
          AND projection_version = $5
          AND resolved_at IS NULL
          AND (locked_by IS NULL OR lease_expires_at <= NOW())
        """,
        tenant_id,
        source_event_ids,
        workflow_id,
        projection_name,
        projection_version,
    )
    return int(str(status).rsplit(" ", 1)[-1])


# --- Fetch sealed-event metadata after a checkpoint (never ciphertext) ---
async def fetch_meta_after_checkpoint(
    pool: asyncpg.Pool | asyncpg.Connection,
    *,
    tenant_id: UUID,
    after_created_at: datetime | None,
    after_event_id: UUID | None,
    workflow_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses = ["tenant_id = $1::uuid"]
    args: list[Any] = [str(tenant_id)]
    canon_wf = canonical_workflow_id(workflow_id)
    if canon_wf:
        args.append(canon_wf)
        clauses.append(f"workflow_id = ${len(args)}")
    if after_created_at is not None and after_event_id is not None:
        args.append(after_created_at)
        created_ph = len(args)
        args.append(str(after_event_id))
        event_ph = len(args)
        clauses.append(f"(created_at, id) > (${created_ph}, ${event_ph}::uuid)")
    elif after_created_at is not None:
        args.append(after_created_at)
        clauses.append(f"created_at > ${len(args)}")
    elif after_event_id is not None:
        args.append(str(after_event_id))
        eid_ph = len(args)
        clauses.append(
            f"(created_at, id) > (SELECT created_at, id FROM telemetry_events"
            f" WHERE id = ${eid_ph}::uuid AND tenant_id = $1::uuid)"
        )
    args.append(limit)
    limit_ph = len(args)
    where = " AND ".join(clauses)
    rows = await pool.fetch(
        f"""
        SELECT id::text, tenant_id::text, key_id, content_type, event_type,
               workflow_id, created_at, ciphertext_bytes AS cipher_len
        FROM telemetry_events
        WHERE {where}
        ORDER BY created_at ASC, id ASC
        LIMIT ${limit_ph}
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


# --- Durable upsert of projection rows ---
async def upsert_stream_results(
    pool: asyncpg.Pool | asyncpg.Connection,
    rows: list[dict[str, Any]],
    *,
    projection_version: int = 1,
    aggregate_event_ids: list[str] | None = None,
    aggregate_event_ids_by_tenant: dict[str, list[str]] | None = None,
    expected_tenant_ids: set[str] | None = None,
    expected_event_ids: set[str] | None = None,
) -> int:
    """Atomically upsert deterministic projection rows.

    Engine output is treated as untrusted: callers can bind accepted tenant and
    source event ids, preventing a malformed remote result from crossing scope.
    """
    if not rows:
        return 0
    expected_tenants = {str(value) for value in (expected_tenant_ids or set())}
    expected_events = {str(value) for value in (expected_event_ids or set())}
    prepared: list[tuple[Any, ...]] = []
    for row in rows:
        tid = row.get("tenant_id")
        if not tid:
            continue
        tid = str(tid)
        if expected_tenants and tid not in expected_tenants:
            raise ValueError("projection output tenant_id was not in the accepted batch")
        source_id = row.get("source_event_id") or row.get("telemetry_event_id")
        if source_id == "":
            source_id = None
        if source_id is not None:
            source_id = str(source_id)
            if expected_events and source_id not in expected_events:
                raise ValueError("projection output source_event_id was not in the accepted batch")
        proj = str(row.get("projection_name") or "sealed.default")
        meta = dict(row.get("metadata") or {})
        if row.get("workflow_id"):
            meta.setdefault("workflow_id", row["workflow_id"])
        meta.setdefault("projection_name", proj)
        tenant_aggregate_ids = aggregate_event_ids
        if aggregate_event_ids_by_tenant is not None:
            tenant_aggregate_ids = aggregate_event_ids_by_tenant.get(tid, [])
        result_key = _projection_result_key(
            row,
            projection_name=proj,
            projection_version=projection_version,
            aggregate_event_ids=tenant_aggregate_ids,
        )
        prepared.append(
            (
                tid,
                source_id,
                str(row.get("kind") or ("transform" if source_id else "rollup")),
                str(row.get("engine") or "pathway"),
                row.get("score"),
                bool(row.get("is_anomaly")),
                _json_dumps(row.get("features") or {}),
                _json_dumps(meta),
                row.get("workflow_id"),
                proj,
                projection_version,
                result_key,
            )
        )

    async def _write(executor: asyncpg.Pool | asyncpg.Connection) -> int:
        for values in prepared:
            await executor.execute(
                """
                INSERT INTO stream_results (
                    tenant_id, telemetry_event_id, source_event_id,
                    kind, engine, score, is_anomaly, features, metadata,
                    workflow_id, projection_name, projection_version,
                    projection_result_key
                )
                VALUES (
                    $1::uuid, $2::uuid, $2::uuid,
                    $3, $4, $5, $6, $7::jsonb, $8::jsonb,
                    $9, $10, $11, $12
                )
                ON CONFLICT (
                    tenant_id, projection_name, projection_version, projection_result_key
                ) DO UPDATE SET
                    telemetry_event_id = EXCLUDED.telemetry_event_id,
                    source_event_id = EXCLUDED.source_event_id,
                    kind = EXCLUDED.kind,
                    engine = EXCLUDED.engine,
                    score = EXCLUDED.score,
                    is_anomaly = EXCLUDED.is_anomaly,
                    features = EXCLUDED.features,
                    metadata = EXCLUDED.metadata,
                    workflow_id = EXCLUDED.workflow_id
                """,
                *values,
            )
        return len(prepared)

    if isinstance(pool, asyncpg.Pool):
        async with pool.acquire() as conn, conn.transaction():
            return await _write(conn)
    return await _write(pool)


# --- Checkpoint helpers ---
async def get_checkpoint(
    pool: asyncpg.Pool | asyncpg.Connection,
    *,
    tenant_id: UUID,
    projection_name: str,
    workflow_id: str = "",
) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        """
        SELECT tenant_id::text, projection_name, workflow_id,
               last_event_id::text, last_created_at, updated_at
        FROM projection_checkpoints
        WHERE tenant_id = $1::uuid
          AND projection_name = $2
          AND workflow_id = $3
        """,
        str(tenant_id),
        projection_name,
        workflow_id or "",
    )
    if row is None:
        return None
    return {
        "tenant_id": row["tenant_id"],
        "projection_name": row["projection_name"],
        "workflow_id": row["workflow_id"],
        "last_event_id": row["last_event_id"],
        "last_created_at": (row["last_created_at"].isoformat() if row["last_created_at"] else None),
        "updated_at": row["updated_at"].isoformat(),
    }


async def advance_checkpoint(
    pool: asyncpg.Pool | asyncpg.Connection,
    *,
    tenant_id: UUID,
    projection_name: str,
    workflow_id: str,
    last_event_id: str,
    last_created_at: datetime,
) -> None:
    await pool.execute(
        """
        INSERT INTO projection_checkpoints (
            tenant_id, projection_name, workflow_id,
            last_event_id, last_created_at, updated_at
        )
        VALUES ($1::uuid, $2, $3, $4::uuid, $5, NOW())
        ON CONFLICT (tenant_id, projection_name, workflow_id) DO UPDATE SET
            last_event_id = EXCLUDED.last_event_id,
            last_created_at = EXCLUDED.last_created_at,
            updated_at = NOW()
        WHERE projection_checkpoints.last_created_at IS NULL
           OR projection_checkpoints.last_event_id IS NULL
           OR (EXCLUDED.last_created_at, EXCLUDED.last_event_id)
              > (projection_checkpoints.last_created_at, projection_checkpoints.last_event_id)
        """,
        str(tenant_id),
        projection_name,
        workflow_id or "",
        last_event_id,
        last_created_at,
    )


# --- Advance watermarks after live ingest (per tenant in meta batch) ---
async def advance_checkpoint_from_meta(
    pool: asyncpg.Pool | asyncpg.Connection,
    *,
    meta_rows: list[dict[str, Any]],
    workflow_id: str,
    projection_name: str | None = None,
) -> None:
    """Stamp projection checkpoints from ingest metadata (no ciphertext)."""
    if not meta_rows:
        return
    proj_name = projection_name
    if not proj_name:
        wf = resolve_workflow(
            content_type=str(meta_rows[0].get("content_type") or "application/forjd-event+v1"),
            event_type=meta_rows[0].get("event_type") or None,
            workflow_id=workflow_id,
        )
        proj_name = wf.pipeline.projection_name
    # Latest tuple per tenant; never rely on request order.
    latest: dict[str, dict[str, Any]] = {}
    for row in meta_rows:
        tid = str(row.get("tenant_id") or "")
        if not tid or not row.get("event_id"):
            continue
        created = row.get("created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                created = None
        if created is None:
            created = await pool.fetchval(
                """
                SELECT created_at FROM telemetry_events
                WHERE id = $1::uuid AND tenant_id = $2::uuid
                """,
                str(row["event_id"]),
                tid,
            )
            if created is None:
                continue
            row = {**row, "created_at": created}
        elif created is not row.get("created_at"):
            row = {**row, "created_at": created}
        current = latest.get(tid)
        if current is None or (created, str(row["event_id"])) > (
            current["created_at"],
            str(current["event_id"]),
        ):
            latest[tid] = row
    for tid, row in latest.items():
        await advance_checkpoint(
            pool,
            tenant_id=UUID(tid),
            projection_name=proj_name,
            workflow_id=workflow_id,
            last_event_id=str(row["event_id"]),
            last_created_at=row["created_at"],
        )


# --- Core projection run (no membership check — caller must authorize) ---
async def run_projection_core(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    workflow_id: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Advance a durable projection from sealed metadata only.

    Intended for: (1) user-facing API after `require_member`, (2) background
    workers using the service-role pool (no synthetic AuthUser).
    """
    await tenant_svc.ensure_secure_schema(pool)
    limit = max(1, min(limit, 1000))

    content_type = "application/forjd-event+v1"
    if workflow_id:
        wf = resolve_workflow(content_type=content_type, workflow_id=workflow_id)
    else:
        wf = resolve_workflow(content_type=content_type)
    proj_name = wf.pipeline.projection_name
    proj_version = wf.pipeline.projection.version
    wf_key = wf.id
    lease_name = projection_lease_name(
        tenant_id=tenant_id,
        projection_name=proj_name,
        workflow_id=wf_key,
    )
    acceptance_fence = projection_acceptance_fence_name(
        tenant_id=tenant_id,
        projection_name=proj_name,
        workflow_id=wf_key,
    )
    meta: list[dict[str, Any]] = []

    async with pool.acquire() as conn:
        leased = await conn.fetchval(
            "SELECT pg_try_advisory_lock(hashtextextended($1, 0))",
            lease_name,
        )
        if not leased:
            return {
                "ok": True,
                "processed": 0,
                "written": 0,
                "leased_elsewhere": True,
                "projection_name": proj_name,
                "workflow_id": wf_key,
            }

        try:
            # Briefly fence canonical acceptance while taking the cursor
            # snapshot. The long-running processor lease remains separate, so
            # ingest never waits on Rust/Pathway/Prefect execution.
            async with conn.transaction():
                await conn.fetchval(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    acceptance_fence,
                )
                ckpt = await get_checkpoint(
                    conn,
                    tenant_id=tenant_id,
                    projection_name=proj_name,
                    workflow_id=wf_key,
                )
                after_ts = None
                after_id = None
                if ckpt and ckpt.get("last_created_at"):
                    after_ts = datetime.fromisoformat(ckpt["last_created_at"])
                if ckpt and ckpt.get("last_event_id"):
                    after_id = UUID(ckpt["last_event_id"])

                meta = await fetch_meta_after_checkpoint(
                    conn,
                    tenant_id=tenant_id,
                    after_created_at=after_ts,
                    after_event_id=after_id,
                    workflow_id=wf_key,
                    limit=limit,
                )
            if not meta:
                return {
                    "ok": True,
                    "processed": 0,
                    "written": 0,
                    "projection_name": proj_name,
                    "workflow_id": wf_key,
                    "checkpoint": ckpt,
                }

            flow = await asyncio.to_thread(
                run_project_flow,
                tenant_id=str(tenant_id),
                events=meta,
                content_type=meta[0]["content_type"],
                event_type=meta[0].get("event_type") or None,
                workflow_id=wf_key,
            )
            pathway = flow.get("pathway") or {}
            pathway_ok = bool(pathway.get("ok"))
            rows = flow.get("stream_results") or []
            event_ids = {str(row["event_id"]) for row in meta}
            failure_error: str | None = None

            async with conn.transaction():
                if pathway_ok:
                    written = await upsert_stream_results(
                        conn,
                        rows,
                        projection_version=proj_version,
                        aggregate_event_ids=sorted(event_ids),
                        expected_tenant_ids={str(tenant_id)},
                        expected_event_ids=event_ids,
                    )
                    await resolve_projection_dlq_for_events(
                        conn,
                        tenant_id=str(tenant_id),
                        source_event_ids=sorted(event_ids),
                        workflow_id=wf_key,
                        projection_name=proj_name,
                        projection_version=proj_version,
                    )
                    last = meta[-1]
                    await advance_checkpoint(
                        conn,
                        tenant_id=tenant_id,
                        projection_name=proj_name,
                        workflow_id=wf_key,
                        last_event_id=str(last["event_id"]),
                        last_created_at=last["created_at"],
                    )
                else:
                    written = 0
                    failure_error = str(
                        pathway.get("error") or "processor reported an unsuccessful result"
                    )
                    for item in meta:
                        await enqueue_projection_dlq(
                            conn,
                            tenant_id=str(tenant_id),
                            source_event_id=str(item["event_id"]),
                            workflow_id=wf_key,
                            projection_name=proj_name,
                            projection_version=proj_version,
                            error=failure_error,
                            payload_meta=item,
                        )
                    # DLQ handoff and cursor movement are atomic: poison events
                    # leave the live lane but remain exactly replayable.
                    last = meta[-1]
                    await advance_checkpoint(
                        conn,
                        tenant_id=tenant_id,
                        projection_name=proj_name,
                        workflow_id=wf_key,
                        last_event_id=str(last["event_id"]),
                        last_created_at=last["created_at"],
                    )

            return {
                "ok": pathway_ok,
                "processed": len(meta) if pathway_ok else 0,
                "matched": len(meta),
                "written": written,
                "projection_name": proj_name,
                "projection_version": proj_version,
                "workflow_id": wf_key,
                "anomaly_count": pathway.get("anomaly_count", 0),
                "dlq_enqueued": 0 if pathway_ok else len(meta),
                "error": failure_error,
                "prefect": {
                    key: value
                    for key, value in flow.items()
                    if key not in {"pathway", "stream_results"}
                },
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "projection failed tenant=%s workflow=%s projection=%s",
                tenant_id,
                wf_key,
                proj_name,
            )
            if meta:
                async with conn.transaction():
                    for item in meta:
                        await enqueue_projection_dlq(
                            conn,
                            tenant_id=str(tenant_id),
                            source_event_id=str(item["event_id"]),
                            workflow_id=wf_key,
                            projection_name=proj_name,
                            projection_version=proj_version,
                            error=str(exc),
                            payload_meta=item,
                        )
                    last = meta[-1]
                    await advance_checkpoint(
                        conn,
                        tenant_id=tenant_id,
                        projection_name=proj_name,
                        workflow_id=wf_key,
                        last_event_id=str(last["event_id"]),
                        last_created_at=last["created_at"],
                    )
            return {
                "ok": False,
                "processed": 0,
                "matched": len(meta),
                "written": 0,
                "projection_name": proj_name,
                "projection_version": proj_version,
                "workflow_id": wf_key,
                "error": str(exc),
                "dlq_enqueued": len(meta),
            }
        finally:
            try:
                await conn.fetchval(
                    "SELECT pg_advisory_unlock(hashtextextended($1, 0))",
                    lease_name,
                )
            except Exception:  # noqa: BLE001
                logger.warning("projection advisory unlock failed lease=%s", lease_name)


# --- User-facing projection (membership gated) ---
async def run_projection(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    workflow_id: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"projections:run"}),
    )
    return await run_projection_core(
        pool,
        tenant_id=tenant_id,
        workflow_id=workflow_id,
        limit=limit,
    )


# --- List durable projection rows ---
async def list_projections(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    projection_name: str | None = None,
    workflow_id: str | None = None,
    since: datetime | None = None,
    after_id: UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List durable projection rows for any SaaS consumer (cursor via since/after_id)."""
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"projections:read"}),
    )
    clauses = ["tenant_id = $1::uuid"]
    args: list[Any] = [str(tenant_id)]
    if projection_name:
        args.append(projection_name)
        clauses.append(f"projection_name = ${len(args)}")
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
    # Live feed (since/after) is ascending; dashboard "latest" is descending.
    order = "ASC" if (since is not None or after_id is not None) else "DESC"
    args.append(limit)
    limit_ph = len(args)
    rows = await pool.fetch(
        f"""
        SELECT id::text, tenant_id::text, telemetry_event_id::text, source_event_id::text,
               created_at, kind, engine, score, is_anomaly, features, metadata,
               workflow_id, projection_name, projection_version,
               projection_result_key
        FROM stream_results
        WHERE {" AND ".join(clauses)}
        ORDER BY created_at {order}, id {order}
        LIMIT ${limit_ph}
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
