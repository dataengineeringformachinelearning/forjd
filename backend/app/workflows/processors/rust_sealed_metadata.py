"""Rust-backed sealed metadata processor (explicit workflow.pipeline.processor)."""

from __future__ import annotations

from typing import Any

from app.services import stream
from app.workflows.models import WorkflowDefinition


# --- Entry used by workflow registry ---
def process(
    events: list[dict[str, Any]],
    workflow: WorkflowDefinition,
) -> dict[str, Any]:
    """Force prefer_rust=True; still falls back to Pathway if engine unavailable."""
    return stream.pathway_sealed_process(events, workflow=workflow, prefer_rust=True)
