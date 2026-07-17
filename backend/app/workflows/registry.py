"""Resolve content_type / event_type / workflow_id → WorkflowDefinition."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings
from app.workflows.loader import load_workflows_dir
from app.workflows.models import WorkflowDefinition

logger = logging.getLogger("forjd.workflows")

_CACHE: list[WorkflowDefinition] | None = None


# --- Path resolution ---
def workflows_dir() -> Path:
    raw = Path(settings.WORKFLOWS_DIR)
    if raw.is_absolute():
        return raw
    # Prefer cwd (Docker WORKDIR=/app, local `cd backend`), then package parent.
    cwd_candidate = Path.cwd() / raw
    if cwd_candidate.is_dir():
        return cwd_candidate
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / raw


# --- Cache ---
def clear_cache() -> None:
    global _CACHE
    _CACHE = None


def all_workflows(*, reload: bool = False) -> list[WorkflowDefinition]:
    global _CACHE
    if _CACHE is None or reload:
        loaded = load_workflows_dir(workflows_dir())
        # Built-in fallback so the platform boots with zero files on disk.
        if not loaded:
            loaded = [_builtin_default()]
            logger.warning("no workflow files found; using built-in default_sealed")
        _CACHE = loaded
    return list(_CACHE)


def _builtin_default() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="default_sealed",
        name="Default sealed stream",
        description="Built-in fallback when workflows/ is empty",
        default=True,
        match={"content_types": ["application/forjd-event+v1"]},
    )


# --- Resolution ---
def get_workflow(workflow_id: str) -> WorkflowDefinition | None:
    wid = workflow_id.strip().lower()
    for wf in all_workflows():
        if wf.id == wid and wf.enabled:
            return wf
    return None


def resolve_workflow(
    *,
    content_type: str,
    event_type: str | None = None,
    workflow_id: str | None = None,
) -> WorkflowDefinition:
    """Pick a workflow for an ingest event.

    Priority: explicit workflow_id → content_type+event_type match → default flag.
    """
    workflows = [w for w in all_workflows() if w.enabled]

    if workflow_id:
        wf = get_workflow(workflow_id)
        if wf is None:
            raise ValueError(f"unknown or disabled workflow_id={workflow_id!r}")
        return wf

    ct = content_type.strip().lower()
    et = (event_type or "").strip().lower() or None

    matches: list[WorkflowDefinition] = []
    for wf in workflows:
        ctypes = [c.lower() for c in wf.match.content_types]
        if ctypes and ct not in ctypes:
            continue
        etypes = [e.lower() for e in wf.match.event_types]
        if etypes and (et is None or et not in etypes):
            continue
        matches.append(wf)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Prefer the most specific event_type match, then first by id.
        specific = [m for m in matches if m.match.event_types]
        pool = specific or matches
        return sorted(pool, key=lambda w: w.id)[0]

    for wf in workflows:
        if wf.default:
            return wf

    raise ValueError(
        f"no workflow matched content_type={content_type!r} event_type={event_type!r}"
    )


def list_workflow_summaries() -> list[dict[str, object]]:
    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "version": w.version,
            "enabled": w.enabled,
            "default": w.default,
            "content_types": w.match.content_types,
            "event_types": w.match.event_types,
            "processor": w.pipeline.processor,
            "steps": w.pipeline.steps,
        }
        for w in all_workflows()
    ]
