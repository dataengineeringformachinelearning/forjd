"""Sealed-event metadata consumer (server-blind, use-case agnostic).

Operates only on non-sensitive fields. Never decrypts ciphertext.
Prefers Rust ``forjd-engine`` sealed pipeline; falls back to pure Python.
"""

from __future__ import annotations

from typing import Any

from app.services import engine as engine_svc
from app.workflows.detectors import run_detectors
from app.workflows.models import WorkflowDefinition


# --- Prefer Rust engine; deterministic Python fallback ---
def pathway_sealed_process(
    events: list[dict[str, Any]],
    *,
    workflow: WorkflowDefinition | None = None,
    prefer_rust: bool = True,
) -> dict[str, Any]:
    """Rollup + configured anomaly detectors on each ingest/project batch.

    Live path: called from Prefect on ingest (and projection ticks). Prefers the
    Rust sealed pipeline (PyO3 or ENGINE_URL). Soft-falls back to pure Python.
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
        "projection_name": (workflow.pipeline.projection_name if workflow else "sealed.default"),
    }
    if not events:
        return empty

    steps = list(workflow.pipeline.steps) if workflow else ["rollup", "size_anomaly"]
    step_set = set(steps)
    tags = dict(workflow.outputs.tags) if workflow else {"use_case": "generic"}
    projection_name = workflow.pipeline.projection_name if workflow else "sealed.default"
    if workflow:
        tags.setdefault("workflow_id", workflow.id)
        tags.setdefault("projection_name", projection_name)

    sanitized = _sanitize(events)

    if prefer_rust:
        rust_out = engine_svc.run_sealed_pipeline_sync(
            sanitized,
            steps=steps,
            params=workflow.pipeline.params_for_detectors() if workflow else {},
            tags=tags,
            projection_name=projection_name,
            workflow_id=workflow.id if workflow else None,
        )
        if rust_out is not None:
            return rust_out
    rollup = (
        _python_rollup(sanitized)
        if "rollup" in step_set
        else {
            "ok": True,
            "engine": "skipped",
            "count": len(sanitized),
            "tenants": len({r["tenant_id"] for r in sanitized}),
            "by_tenant": {},
        }
    )

    params_by_step = workflow.pipeline.params_for_detectors() if workflow is not None else {}
    anomalies = run_detectors(sanitized, steps=steps, params_by_step=params_by_step)

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


_ROUTING_KEYS = frozenset(
    {
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
)


# --- Column sanitize (reject anything that looks like ciphertext) ---
def _sanitize(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for e in events:
        raw_meta = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
        routing = {k: v for k, v in raw_meta.items() if k in _ROUTING_KEYS}
        rows.append(
            {
                "event_id": str(e.get("event_id") or ""),
                "tenant_id": str(e.get("tenant_id") or ""),
                "key_id": str(e.get("key_id") or ""),
                "cipher_len": int(e.get("cipher_len") or 0),
                "content_type": str(e.get("content_type") or ""),
                "event_type": str(e.get("event_type") or ""),
                "workflow_id": str(e.get("workflow_id") or ""),
                "metadata": routing,
                # Flatten common tags so detectors/analytics can read them cheaply.
                "region": str(routing.get("region") or "")[:128],
                "component": str(routing.get("component") or "")[:128],
                "label": str(routing.get("label") or "")[:128],
                "source": str(routing.get("source") or "")[:128],
            }
        )
    return rows


# --- Flatten into durable stream_results shapes ---
def _to_stream_result_rows(
    rollup: dict[str, Any],
    anomalies: list[dict[str, Any]],
    *,
    tags: dict[str, Any],
    steps: set[str],
    projection_name: str,
) -> list[dict[str, Any]]:
    engine = str(rollup.get("engine") or "python-fallback")
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
        row_meta = dict(base_meta)
        for key in ("region", "component", "label", "source"):
            value = a.get(key)
            if value:
                row_meta[key] = value
        extra = a.get("metadata") if isinstance(a.get("metadata"), dict) else {}
        for key, value in extra.items():
            if key in _ROUTING_KEYS and value is not None:
                row_meta[key] = value
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
                "metadata": row_meta,
                "workflow_id": tags.get("workflow_id"),
            }
        )
    return rows


# --- Dependency-free fallback when Rust is unavailable ---
def _python_rollup(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_tenant: dict[str, dict[str, int]] = {}
    for e in events:
        tid = str(e.get("tenant_id", ""))
        slot = by_tenant.setdefault(tid, {"count": 0, "bytes": 0, "max_cipher_len": 0})
        clen = int(e.get("cipher_len") or 0)
        slot["count"] += 1
        slot["bytes"] += clen
        slot["max_cipher_len"] = max(slot["max_cipher_len"], clen)
    return {
        "ok": True,
        "engine": "python-fallback",
        "count": len(events),
        "tenants": len(by_tenant),
        "by_tenant": by_tenant,
    }
