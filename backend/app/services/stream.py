"""Pathway consumer for sealed-event metadata (server-blind, use-case agnostic).

Operates only on non-sensitive fields. Never decrypts ciphertext.
Rollup uses Pathway; anomaly steps use the pluggable detector registry.
"""

from __future__ import annotations

import logging
from typing import Any

from app.workflows.detectors import run_detectors
from app.workflows.models import WorkflowDefinition

logger = logging.getLogger("forjd.stream")


# --- Pathway transform + pluggable detectors (ciphertext never enters) ---
def pathway_sealed_process(
    events: list[dict[str, Any]],
    *,
    workflow: WorkflowDefinition | None = None,
) -> dict[str, Any]:
    """Pathway reduce + configured anomaly detectors on each ingest/project batch.

    Live path: called from Prefect on ingest (and projection ticks). Soft-fails
    when Pathway is unavailable (same pattern as pulse). Continuous jobs can
    be layered later; watermarks stay correct via projection checkpoints.
    """
    empty = {
        "ok": True,
        "count": 0,
        "tenants": 0,
        "by_tenant": {},
        "anomalies": [],
        "results": [],
        "anomaly_count": 0,
        "workflow_id": workflow.id if workflow else None,
        "projection_name": (
            workflow.pipeline.projection_name if workflow else "sealed.default"
        ),
    }
    if not events:
        return empty

    steps = list(workflow.pipeline.steps) if workflow else ["rollup", "size_anomaly"]
    step_set = set(steps)
    tags = dict(workflow.outputs.tags) if workflow else {"use_case": "generic"}
    projection_name = (
        workflow.pipeline.projection_name if workflow else "sealed.default"
    )
    if workflow:
        tags.setdefault("workflow_id", workflow.id)
        tags.setdefault("projection_name", projection_name)

    sanitized = _sanitize(events)
    rollup = (
        _pathway_rollup(sanitized)
        if "rollup" in step_set
        else {
            "ok": True,
            "engine": "skipped",
            "count": len(sanitized),
            "tenants": len({r["tenant_id"] for r in sanitized}),
            "by_tenant": {},
        }
    )

    params_by_step = (
        workflow.pipeline.params_for_detectors() if workflow is not None else {}
    )
    anomalies = run_detectors(
        sanitized, steps=steps, params_by_step=params_by_step
    )

    results = _to_stream_result_rows(
        rollup,
        anomalies,
        tags=tags,
        steps=step_set,
        projection_name=projection_name,
    )
    return {
        **rollup,
        "anomalies": anomalies,
        "results": results,
        "anomaly_count": sum(1 for a in anomalies if a.get("is_anomaly")),
        "workflow_id": workflow.id if workflow else None,
        "projection_name": projection_name,
    }


def pathway_sealed_rollup(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Backward-compatible alias — prefer pathway_sealed_process."""
    out = pathway_sealed_process(events)
    return {
        "ok": out.get("ok", False),
        "engine": out.get("engine"),
        "count": out.get("count", 0),
        "tenants": out.get("tenants", 0),
        "by_tenant": out.get("by_tenant", {}),
        "error": out.get("error"),
    }


# --- Column sanitize (reject anything that looks like ciphertext) ---
def _sanitize(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for e in events:
        rows.append(
            {
                "event_id": str(e.get("event_id") or ""),
                "tenant_id": str(e.get("tenant_id") or ""),
                "key_id": str(e.get("key_id") or ""),
                "cipher_len": int(e.get("cipher_len") or 0),
                "content_type": str(e.get("content_type") or ""),
                "event_type": str(e.get("event_type") or ""),
                "workflow_id": str(e.get("workflow_id") or ""),
            }
        )
    return rows


# --- Pathway groupby rollup ---
def _pathway_rollup(rows: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import pandas as pd
        import pathway as pw
    except Exception as exc:  # pragma: no cover
        logger.warning("pathway unavailable: %s", exc)
        return _python_rollup(rows, error=str(exc))

    try:
        table = pw.debug.table_from_pandas(pd.DataFrame(rows))
        reduced = table.groupby(pw.this.tenant_id).reduce(
            tenant_id=pw.this.tenant_id,
            count=pw.reducers.count(),
            bytes=pw.reducers.sum(pw.this.cipher_len),
            max_cipher_len=pw.reducers.max(pw.this.cipher_len),
        )
        frame = pw.debug.table_to_pandas(reduced)
        by_tenant: dict[str, Any] = {}
        for _, row in frame.iterrows():
            by_tenant[str(row["tenant_id"])] = {
                "count": int(row["count"]),
                "bytes": int(row["bytes"]),
                "max_cipher_len": int(row["max_cipher_len"]),
            }
        return {
            "ok": True,
            "engine": "pathway",
            "count": sum(v["count"] for v in by_tenant.values()),
            "tenants": len(by_tenant),
            "by_tenant": by_tenant,
        }
    except Exception as exc:
        logger.exception("pathway sealed rollup failed")
        return _python_rollup(rows, error=str(exc))


# --- Flatten into durable stream_results shapes ---
def _to_stream_result_rows(
    rollup: dict[str, Any],
    anomalies: list[dict[str, Any]],
    *,
    tags: dict[str, Any],
    steps: set[str],
    projection_name: str,
) -> list[dict[str, Any]]:
    engine = str(rollup.get("engine") or "pathway")
    rows: list[dict[str, Any]] = []
    base_meta = {"source": "forjd-ingest", **tags}

    if "rollup" in steps:
        for tid, stats in (rollup.get("by_tenant") or {}).items():
            rows.append(
                {
                    "tenant_id": tid,
                    "telemetry_event_id": None,
                    "source_event_id": None,
                    "kind": "rollup",
                    "engine": engine,
                    "score": None,
                    "is_anomaly": False,
                    "projection_name": projection_name,
                    "features": {
                        "count": stats.get("count"),
                        "bytes": stats.get("bytes"),
                        "max_cipher_len": stats.get("max_cipher_len"),
                    },
                    "metadata": dict(base_meta),
                    "workflow_id": tags.get("workflow_id"),
                }
            )

    for a in anomalies:
        eid = a.get("event_id") or None
        if eid == "":
            eid = None
        rows.append(
            {
                "tenant_id": a["tenant_id"],
                "telemetry_event_id": eid,
                "source_event_id": eid,
                "kind": "anomaly" if a.get("is_anomaly") else "transform",
                "engine": engine,
                "score": a.get("score"),
                "is_anomaly": bool(a.get("is_anomaly")),
                "projection_name": projection_name,
                "features": {
                    "key_id": a.get("key_id"),
                    "cipher_len": a.get("cipher_len"),
                    "z_score": a.get("z_score"),
                    "batch_count": a.get("batch_count"),
                    "detector": a.get("detector"),
                    "reason": a.get("reason"),
                },
                "metadata": dict(base_meta),
                "workflow_id": tags.get("workflow_id"),
            }
        )
    return rows


# --- Fallback when Pathway import/runtime fails ---
def _python_rollup(
    events: list[dict[str, Any]], *, error: str | None = None
) -> dict[str, Any]:
    by_tenant: dict[str, dict[str, int]] = {}
    for e in events:
        tid = str(e.get("tenant_id", ""))
        slot = by_tenant.setdefault(
            tid, {"count": 0, "bytes": 0, "max_cipher_len": 0}
        )
        clen = int(e.get("cipher_len") or 0)
        slot["count"] += 1
        slot["bytes"] += clen
        slot["max_cipher_len"] = max(slot["max_cipher_len"], clen)
    out: dict[str, Any] = {
        "ok": error is None,
        "engine": "python-fallback",
        "count": len(events),
        "tenants": len(by_tenant),
        "by_tenant": by_tenant,
    }
    if error:
        out["error"] = error
    return out
