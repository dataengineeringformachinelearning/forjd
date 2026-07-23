"""Default processor: Rust sealed pipeline (pure-Python soft-fallback).

Config-driven via YAML ``pipeline.processor: sealed_metadata``. Operates on
cipher lengths + routing metadata only — never decrypts.
"""

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
