"""Load workflow definitions from YAML/JSON on disk."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from app.workflows.models import WorkflowDefinition

logger = logging.getLogger("forjd.workflows")


# --- Parse one file ---
def load_workflow_file(path: Path) -> WorkflowDefinition:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        raw: Any = yaml.safe_load(text)
    elif suffix == ".json":
        raw = json.loads(text)
    else:
        raise ValueError(f"unsupported workflow format: {path}")
    if not isinstance(raw, dict):
        raise ValueError(f"workflow root must be a mapping: {path}")
    return WorkflowDefinition.model_validate(raw)


# --- Scan directory ---
def load_workflows_dir(directory: Path) -> list[WorkflowDefinition]:
    if not directory.is_dir():
        logger.warning("workflows dir missing: %s", directory)
        return []

    found: list[WorkflowDefinition] = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in {".yaml", ".yml", ".json"}:
            continue
        if path.is_dir():
            continue
        try:
            found.append(load_workflow_file(path))
        except Exception as exc:  # noqa: BLE001
            logger.exception("failed to load workflow %s: %s", path, exc)
    return found
