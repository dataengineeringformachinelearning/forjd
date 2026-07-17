"""Prefect flow for configurable sealed-stream ingest.

Loads a WorkflowDefinition (YAML/JSON), runs the registered processor
(Pathway by default), and returns result rows for Supabase persistence.
Soft-fails when Prefect API is offline (same pattern as pulse).
"""

from __future__ import annotations

from typing import Any

from prefect import flow, task

from app.pipelines.soft_fail import run_with_local_fallback
from app.workflows.processors import get_processor
from app.workflows.registry import resolve_workflow


# --- Prefect task: resolve + run configured processor ---
@task(name="ingest-process-workflow")
def process_with_workflow(
    events: list[dict[str, Any]],
    *,
    content_type: str,
    event_type: str | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    """Run the workflow's processor on sealed metadata only."""
    workflow = resolve_workflow(
        content_type=content_type,
        event_type=event_type,
        workflow_id=workflow_id,
    )
    processor = get_processor(workflow.pipeline.processor)
    out = processor(events, workflow)
    out["workflow_id"] = workflow.id
    out["processor"] = workflow.pipeline.processor
    return out


# --- Prefect task: ack for observability ---
@task(name="ingest-ack")
def ack_ingest(
    user_id: str,
    tenant_ids: list[str],
    accepted: int,
    event_ids: list[str],
    pathway: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pathway = pathway or {}
    return {
        "user_id": user_id,
        "tenant_ids": tenant_ids,
        "accepted": accepted,
        "event_ids": event_ids[:20],
        "workflow_id": pathway.get("workflow_id"),
        "pathway_ok": bool(pathway.get("ok")),
        "pathway_count": int(pathway.get("count") or 0),
        "anomaly_count": int(pathway.get("anomaly_count") or 0),
        "message": (
            f"prefect ingest ack user={user_id[:8]}… "
            f"wf={pathway.get('workflow_id') or '-'} "
            f"tenants={len(tenant_ids)} events={accepted} "
            f"pathway={'ok' if pathway.get('ok') else 'skip'}"
            f"({pathway.get('count') or 0}) "
            f"anomalies={pathway.get('anomaly_count') or 0}"
        ),
    }


# --- Prefect flow: consume → configured processor → result payload ---
@flow(name="forjd-ingest", log_prints=True)
def ingest_flow(
    user_id: str,
    tenant_ids: list[str],
    accepted: int = 0,
    event_ids: list[str] | None = None,
    events: list[dict[str, Any]] | None = None,
    content_type: str = "application/forjd-event+v1",
    event_type: str | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    pathway = process_with_workflow(
        events or [],
        content_type=content_type,
        event_type=event_type,
        workflow_id=workflow_id,
    )
    ack = ack_ingest(
        user_id,
        tenant_ids,
        accepted,
        event_ids or [],
        pathway,
    )
    print(ack["message"])
    return {
        "ok": True,
        **ack,
        "pathway": pathway,
        "stream_results": pathway.get("results") or [],
    }


# --- Entry used by the API (local fallback if Prefect is down) ---
def run_ingest_flow(
    *,
    user_id: str,
    tenant_ids: list[str],
    accepted: int,
    event_ids: list[str],
    events: list[dict[str, Any]] | None = None,
    content_type: str = "application/forjd-event+v1",
    event_type: str | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    def _local(exc: Exception) -> dict[str, Any]:
        pathway = process_with_workflow.fn(
            events or [],
            content_type=content_type,
            event_type=event_type,
            workflow_id=workflow_id,
        )
        body = ack_ingest.fn(
            user_id,
            tenant_ids,
            accepted,
            event_ids,
            pathway,
        )
        return {
            "ok": True,
            "mode": "local-fallback",
            "error": str(exc),
            **body,
            "pathway": pathway,
            "stream_results": pathway.get("results") or [],
        }

    return run_with_local_fallback(
        ingest_flow,
        user_id,
        tenant_ids,
        accepted,
        event_ids,
        events,
        content_type,
        event_type,
        workflow_id,
        fallback=_local,
    )
