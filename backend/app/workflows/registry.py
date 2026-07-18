"""Resolve content_type / event_type / workflow_id → WorkflowDefinition.

Partner / legacy wire ids are config-only: each workflow YAML may declare
``aliases.workflow_ids`` and ``aliases.event_types``. Resolution maps those
onto the canonical workflow id and event types before matching or storage.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings
from app.workflows.detectors import REGISTRY as DETECTOR_REGISTRY
from app.workflows.loader import load_workflows_dir
from app.workflows.models import WorkflowDefinition
from app.workflows.processors import REGISTRY as PROCESSOR_REGISTRY

logger = logging.getLogger("forjd.workflows")

# Built-in non-detector pipeline steps (processor-local).
_BUILTIN_STEPS = frozenset({"rollup"})

_CACHE: list[WorkflowDefinition] | None = None
# workflow_id alias (lowercase) → canonical workflow id
_WORKFLOW_ID_ALIASES: dict[str, str] = {}
# event_type alias (lowercase) → canonical event_type (global across workflows)
_EVENT_TYPE_ALIASES: dict[str, str] = {}
# content_type alias (lowercase) → set of workflow ids that accept it
_CONTENT_TYPE_ALIASES: dict[str, set[str]] = {}


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


# --- Alias index ---
def _alias_clash(kind: str, alias: str, existing: str, claimant: str) -> None:
    """Warn always; fail closed in production so misroutes cannot ship silently."""
    msg = f"{kind} alias {alias!r} claimed by both {existing!r} and {claimant!r}"
    if settings.is_production:
        raise RuntimeError(f"workflow alias collision: {msg}")
    logger.warning("%s; keeping %r", msg, existing)


def _rebuild_alias_index(workflows: list[WorkflowDefinition]) -> None:
    """Build workflow_id / event_type / content_type alias maps from loaded YAML."""
    global _WORKFLOW_ID_ALIASES, _EVENT_TYPE_ALIASES, _CONTENT_TYPE_ALIASES
    wid_map: dict[str, str] = {}
    et_map: dict[str, str] = {}
    ct_map: dict[str, set[str]] = {}

    for wf in workflows:
        if not wf.enabled:
            continue
        # Canonical id always resolves to itself.
        wid_map[wf.id] = wf.id
        for alias in wf.aliases.workflow_ids:
            if alias == wf.id:
                continue
            existing = wid_map.get(alias)
            if existing is not None and existing != wf.id:
                _alias_clash("workflow", alias, existing, wf.id)
                continue
            wid_map[alias] = wf.id

        for canon, aliases in wf.aliases.event_types.items():
            et_map[canon] = canon
            for alias in aliases:
                if alias == canon:
                    continue
                existing = et_map.get(alias)
                if existing is not None and existing != canon:
                    _alias_clash("event_type", alias, existing, canon)
                    continue
                et_map[alias] = canon

        for ct_alias in wf.aliases.content_types:
            owners = ct_map.setdefault(ct_alias, set())
            owners.add(wf.id)

    _WORKFLOW_ID_ALIASES = wid_map
    _EVENT_TYPE_ALIASES = et_map
    _CONTENT_TYPE_ALIASES = ct_map


def canonical_workflow_id(workflow_id: str | None) -> str | None:
    """Return the stored/canonical workflow id for a wire id or alias."""
    if workflow_id is None:
        return None
    key = workflow_id.strip().lower()
    if not key:
        return None
    # Ensure cache (and alias index) is warm.
    all_workflows()
    return _WORKFLOW_ID_ALIASES.get(key, key)


def canonical_event_type(event_type: str | None) -> str | None:
    """Return the canonical event_type for a wire value or alias."""
    if event_type is None:
        return None
    key = event_type.strip().lower()
    if not key:
        return None
    all_workflows()
    return _EVENT_TYPE_ALIASES.get(key, key)


def _filter_event_types(wf: WorkflowDefinition) -> set[str]:
    """Wire event_types allowed by ``match.event_types`` (empty = any).

    Partner aliases expand the set when listed (directly or via their canonical).
    """
    declared = {e.lower() for e in wf.match.event_types}
    if not declared:
        return set()
    accepted = set(declared)
    for canon, aliases in wf.aliases.event_types.items():
        alias_set = set(aliases)
        if canon in accepted or accepted & alias_set:
            accepted.add(canon)
            accepted |= alias_set
    for et in list(accepted):
        canon = _EVENT_TYPE_ALIASES.get(et)
        if canon:
            accepted.add(canon)
    return accepted


# --- Cache ---
def clear_cache() -> None:
    global _CACHE, _WORKFLOW_ID_ALIASES, _EVENT_TYPE_ALIASES, _CONTENT_TYPE_ALIASES
    _CACHE = None
    _WORKFLOW_ID_ALIASES = {}
    _EVENT_TYPE_ALIASES = {}
    _CONTENT_TYPE_ALIASES = {}


def all_workflows(*, reload: bool = False) -> list[WorkflowDefinition]:
    global _CACHE
    if _CACHE is None or reload:
        loaded = load_workflows_dir(workflows_dir())
        # Built-in fallback so the platform boots with zero files on disk.
        if not loaded:
            loaded = [_builtin_default()]
            logger.warning("no workflow files found; using built-in default_sealed")
        for wf in loaded:
            _warn_unknown_extensions(wf)
        _rebuild_alias_index(loaded)
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


def _warn_unknown_extensions(wf: WorkflowDefinition) -> None:
    """Fail soft on unknown processors/detectors so YAML stays extensible."""
    proc = wf.pipeline.processor
    if proc not in PROCESSOR_REGISTRY:
        logger.warning(
            "workflow %s references unknown processor %r; known: %s",
            wf.id,
            proc,
            ", ".join(sorted(PROCESSOR_REGISTRY)) or "(none)",
        )
    for step in wf.pipeline.steps:
        if step in _BUILTIN_STEPS or step in DETECTOR_REGISTRY:
            continue
        logger.warning(
            "workflow %s step %r is not a built-in or registered detector "
            "(will be skipped at runtime)",
            wf.id,
            step,
        )


# --- Resolution ---
def get_workflow(workflow_id: str) -> WorkflowDefinition | None:
    wid = canonical_workflow_id(workflow_id) or workflow_id.strip().lower()
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

    Priority: explicit workflow_id (incl. aliases) → content_type+event_type
    match (aliases expand match sets) → default flag.
    """
    workflows = [w for w in all_workflows() if w.enabled]

    if workflow_id:
        wf = get_workflow(workflow_id)
        if wf is None:
            raise ValueError(f"unknown or disabled workflow_id={workflow_id!r}")
        return wf

    ct = content_type.strip().lower()
    et = (event_type or "").strip().lower() or None
    et_canon = canonical_event_type(et) if et else None
    # Warm alias index for content_type aliases.
    all_workflows()
    ct_alias_owners = _CONTENT_TYPE_ALIASES.get(ct, set())

    matches: list[WorkflowDefinition] = []
    for wf in workflows:
        ctypes = [c.lower() for c in wf.match.content_types]
        alias_hit = wf.id in ct_alias_owners
        if ctypes and ct not in ctypes and not alias_hit:
            continue
        accepted = _filter_event_types(wf)
        # Empty match.event_types = any event_type for this content_type.
        if accepted and (et is None or (et not in accepted and et_canon not in accepted)):
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
            "catalog_event_types": [e.model_dump() for e in w.event_types],
            "aliases": w.aliases.model_dump(),
            "processor": w.pipeline.processor,
            "steps": w.pipeline.steps,
            "projection": (
                w.pipeline.projection.model_dump()
                if w.pipeline.projection
                else {"name": w.pipeline.projection_name, "version": 1}
            ),
            "encryption": w.encryption.model_dump(),
        }
        for w in all_workflows()
    ]
