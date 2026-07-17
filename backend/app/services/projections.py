"""Durable live projections — checkpointed reprocess of sealed metadata.

Mirrors DEML projector concepts: idempotent upserts, watermarks, no plaintext.
Ciphertext stays in telemetry_events; processors see sizes/routing only.
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
from app.services import tenants as tenant_svc
from app.workflows.registry import resolve_workflow

logger = logging.getLogger("forjd.projections")


# --- Fetch sealed-event metadata after a checkpoint (never ciphertext) ---
async def fetch_meta_after_checkpoint(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    after_created_at: datetime | None,
    after_event_id: UUID | None,
    workflow_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses = ["tenant_id = $1::uuid"]
    args: list[Any] = [str(tenant_id)]
    if workflow_id:
        args.append(workflow_id)
        clauses.append(f"workflow_id = ${len(args)}")
    if after_created_at is not None:
        args.append(after_created_at)
        clauses.append(f"created_at > ${len(args)}")
    elif after_event_id is not None:
        args.append(str(after_event_id))
        eid_ph = len(args)
        clauses.append(
            f"created_at >= (SELECT created_at FROM telemetry_events WHERE id = ${eid_ph}::uuid)"
        )
        clauses.append(f"id <> ${eid_ph}::uuid")
    args.append(limit)
    limit_ph = len(args)
    where = " AND ".join(clauses)
    rows = await pool.fetch(
        f"""
        SELECT id::text, tenant_id::text, key_id, content_type, event_type,
               workflow_id, created_at, length(ciphertext) AS cipher_len
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
    pool: asyncpg.Pool,
    rows: list[dict[str, Any]],
) -> int:
    written = 0
    for row in rows:
        tid = row.get("tenant_id")
        if not tid:
            continue
        source_id = row.get("source_event_id") or row.get("telemetry_event_id")
        if source_id == "":
            source_id = None
        proj = str(row.get("projection_name") or "sealed.default")
        meta = dict(row.get("metadata") or {})
        if row.get("workflow_id"):
            meta.setdefault("workflow_id", row["workflow_id"])
        meta.setdefault("projection_name", proj)

        if source_id:
            # Idempotent replace (partial unique index on source_event_id).
            await pool.execute(
                """
                DELETE FROM stream_results
                WHERE tenant_id = $1::uuid
                  AND projection_name = $2
                  AND source_event_id = $3::uuid
                """,
                str(tid),
                proj,
                str(source_id),
            )
            await pool.execute(
                """
                INSERT INTO stream_results (
                    tenant_id, telemetry_event_id, source_event_id,
                    kind, engine, score, is_anomaly, features, metadata,
                    workflow_id, projection_name, projection_version
                )
                VALUES (
                    $1::uuid, $2::uuid, $3::uuid,
                    $4, $5, $6, $7, $8::jsonb, $9::jsonb,
                    $10, $11, 1
                )
                """,
                str(tid),
                str(source_id),
                str(source_id),
                str(row.get("kind") or "transform"),
                str(row.get("engine") or "pathway"),
                row.get("score"),
                bool(row.get("is_anomaly")),
                json.dumps(row.get("features") or {}),
                json.dumps(meta),
                row.get("workflow_id"),
                proj,
            )
        else:
            # Aggregate rollups have no source_event_id — append.
            await pool.execute(
                """
                INSERT INTO stream_results (
                    tenant_id, kind, engine, score, is_anomaly,
                    features, metadata, workflow_id, projection_name
                )
                VALUES (
                    $1::uuid, $2, $3, $4, $5,
                    $6::jsonb, $7::jsonb, $8, $9
                )
                """,
                str(tid),
                str(row.get("kind") or "rollup"),
                str(row.get("engine") or "pathway"),
                row.get("score"),
                bool(row.get("is_anomaly")),
                json.dumps(row.get("features") or {}),
                json.dumps(meta),
                row.get("workflow_id"),
                proj,
            )
        written += 1
    return written


# --- Checkpoint helpers ---
async def get_checkpoint(
    pool: asyncpg.Pool,
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
        "last_created_at": (
            row["last_created_at"].isoformat() if row["last_created_at"] else None
        ),
        "updated_at": row["updated_at"].isoformat(),
    }


async def advance_checkpoint(
    pool: asyncpg.Pool,
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
        """,
        str(tenant_id),
        projection_name,
        workflow_id or "",
        last_event_id,
        last_created_at,
    )


# --- Run projection for a tenant (Prefect soft-fail) ---
async def run_projection(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    workflow_id: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    await tenant_svc.ensure_secure_schema(pool)
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin", "member"}),
    )
    limit = max(1, min(limit, 1000))

    # Resolve workflow for projection name + processor config.
    content_type = "application/forjd-event+v1"
    if workflow_id:
        wf = resolve_workflow(
            content_type=content_type,
            workflow_id=workflow_id,
        )
    else:
        wf = resolve_workflow(content_type=content_type)
    proj_name = wf.pipeline.projection_name
    wf_key = wf.id

    ckpt = await get_checkpoint(
        pool,
        tenant_id=tenant_id,
        projection_name=proj_name,
        workflow_id=wf_key,
    )
    after_ts = None
    after_id = None
    if ckpt and ckpt.get("last_created_at"):
        after_ts = datetime.fromisoformat(ckpt["last_created_at"])
    elif ckpt and ckpt.get("last_event_id"):
        after_id = UUID(ckpt["last_event_id"])

    meta = await fetch_meta_after_checkpoint(
        pool,
        tenant_id=tenant_id,
        after_created_at=after_ts,
        after_event_id=after_id,
        workflow_id=workflow_id,
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

    flow = run_project_flow(
        tenant_id=str(tenant_id),
        events=meta,
        content_type=meta[0]["content_type"],
        event_type=meta[0].get("event_type") or None,
        workflow_id=wf_key,
    )
    pathway = flow.get("pathway") or {}
    rows = flow.get("stream_results") or []
    written = await upsert_stream_results(pool, rows)

    last = meta[-1]
    await advance_checkpoint(
        pool,
        tenant_id=tenant_id,
        projection_name=proj_name,
        workflow_id=wf_key,
        last_event_id=str(last["event_id"]),
        last_created_at=last["created_at"],
    )
    return {
        "ok": True,
        "processed": len(meta),
        "written": written,
        "projection_name": proj_name,
        "workflow_id": wf_key,
        "anomaly_count": pathway.get("anomaly_count", 0),
        "prefect": {k: v for k, v in flow.items() if k not in {"pathway", "stream_results"}},
    }


# --- List durable projection rows ---
async def list_projections(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    projection_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    clauses = ["tenant_id = $1::uuid"]
    args: list[Any] = [str(tenant_id)]
    if projection_name:
        args.append(projection_name)
        clauses.append(f"projection_name = ${len(args)}")
    args.append(limit)
    limit_ph = len(args)
    rows = await pool.fetch(
        f"""
        SELECT id::text, tenant_id::text, telemetry_event_id::text, source_event_id::text,
               created_at, kind, engine, score, is_anomaly, features, metadata,
               workflow_id, projection_name, projection_version
        FROM stream_results
        WHERE {" AND ".join(clauses)}
        ORDER BY created_at DESC
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
            }
        )
    return out
