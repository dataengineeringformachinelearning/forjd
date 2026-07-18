"""Prefect flows for durable projections and replay (soft-fail).

Config-driven: resolves YAML workflow → processor registry (Rust preferred,
Pathway fallback). Same path for catch-up ticks and any other SaaS.
"""

from __future__ import annotations

from typing import Any

from prefect import flow, task

from app.pipelines.soft_fail import run_with_local_fallback
from app.workflows.processors import get_processor
from app.workflows.registry import resolve_workflow


# --- Process sealed metadata with a workflow ---
@task(name="project-process")
def process_projection_batch(
    events: list[dict[str, Any]],
    *,
    content_type: str,
    event_type: str | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    workflow = resolve_workflow(
        content_type=content_type,
        event_type=event_type,
        workflow_id=workflow_id,
    )
    processor = get_processor(workflow.pipeline.processor)
    out = processor(events, workflow)
    out["workflow_id"] = workflow.id
    out["projection_name"] = workflow.pipeline.projection_name
    return out


@flow(name="forjd-project", log_prints=True)
def project_flow(
    tenant_id: str,
    events: list[dict[str, Any]] | None = None,
    content_type: str = "application/forjd-event+v1",
    event_type: str | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    pathway = process_projection_batch(
        events or [],
        content_type=content_type,
        event_type=event_type,
        workflow_id=workflow_id,
    )
    msg = (
        f"project tenant={tenant_id[:8]}… wf={pathway.get('workflow_id')} "
        f"events={pathway.get('count', 0)} anom={pathway.get('anomaly_count', 0)}"
    )
    print(msg)
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "message": msg,
        "pathway": pathway,
        "stream_results": pathway.get("results") or [],
    }


def run_project_flow(
    *,
    tenant_id: str,
    events: list[dict[str, Any]],
    content_type: str = "application/forjd-event+v1",
    event_type: str | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    def _local(exc: Exception) -> dict[str, Any]:
        pathway = process_projection_batch.fn(
            events,
            content_type=content_type,
            event_type=event_type,
            workflow_id=workflow_id,
        )
        return {
            "ok": True,
            "mode": "local-fallback",
            "error": str(exc),
            "tenant_id": tenant_id,
            "pathway": pathway,
            "stream_results": pathway.get("results") or [],
        }

    return run_with_local_fallback(
        project_flow,
        tenant_id,
        events,
        content_type,
        event_type,
        workflow_id,
        fallback=_local,
    )
