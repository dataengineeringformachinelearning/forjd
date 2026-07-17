"""Pluggable anomaly detectors (metadata-only; never open ciphertext).

Register a detector to extend threat/anomaly without forking ingest:
  1. Add `my_detector.py` with `detect(events, params) -> list[dict]`.
  2. Register below.
  3. Enable the step name in a workflow YAML `pipeline.steps`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.workflows.detectors import rate_anomaly, size_anomaly

DetectorFn = Callable[[list[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]]

# --- Detector registry ---
REGISTRY: dict[str, DetectorFn] = {
    "size_anomaly": size_anomaly.detect,
    "rate_anomaly": rate_anomaly.detect,
}


def get_detector(name: str) -> DetectorFn:
    try:
        return REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(sorted(REGISTRY)) or "(none)"
        raise ValueError(f"unknown detector {name!r}; known: {known}") from exc


def run_detectors(
    events: list[dict[str, Any]],
    *,
    steps: list[str],
    params_by_step: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run all detector steps; merge anomaly rows (metadata only)."""
    out: list[dict[str, Any]] = []
    for step in steps:
        if step not in REGISTRY:
            continue
        fn = REGISTRY[step]
        out.extend(fn(events, params_by_step.get(step) or {}))
    return out
