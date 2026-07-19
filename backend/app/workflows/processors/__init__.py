"""Processor registry — map workflow.pipeline.processor → callable.

Add a new use-case processor here without changing ingest/API core:
  1. Implement `process(events, workflow) -> dict` in a new module.
  2. Register it in REGISTRY below.
  3. Point a YAML workflow at that processor name.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.workflows.models import WorkflowDefinition
from app.workflows.processors import sealed_metadata

ProcessorFn = Callable[[list[dict[str, Any]], WorkflowDefinition], dict[str, Any]]

# --- Registered processors (extend without touching ingest routes) ---
REGISTRY: dict[str, ProcessorFn] = {
    # Rust sealed pipeline with Pathway/Python soft-fallback.
    "sealed_metadata": sealed_metadata.process,
}


def get_processor(name: str) -> ProcessorFn:
    try:
        return REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(sorted(REGISTRY)) or "(none)"
        raise ValueError(f"unknown processor {name!r}; known: {known}") from exc
