"""Default processor: Pathway rollup + size anomaly on sealed metadata only."""

from __future__ import annotations

from typing import Any

from app.services import stream
from app.workflows.models import WorkflowDefinition


# --- Entry used by workflow registry ---
def process(
    events: list[dict[str, Any]],
    workflow: WorkflowDefinition,
) -> dict[str, Any]:
    return stream.pathway_sealed_process(events, workflow=workflow)
