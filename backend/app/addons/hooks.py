"""Stable engine lifecycle hooks for optional add-ons.

Add-on modules register small synchronous handlers at import/startup time. The
Prefect task skips disabled add-ons, isolates failures, and returns structured
observability data; optional integrations can therefore never take down the
sealed ingest path.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from prefect import task

from app.addons.registry import addon_enabled, get_addon


class HookPoint(StrEnum):
    BEFORE_WORKFLOW = "before_workflow"
    AFTER_WORKFLOW = "after_workflow"
    WORKFLOW_ERROR = "workflow_error"


HookHandler = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]


@dataclass(frozen=True)
class HookRegistration:
    addon: str
    point: HookPoint
    handler: HookHandler


_HOOKS: list[HookRegistration] = []


def register_hook(addon: str, point: HookPoint, handler: HookHandler) -> None:
    """Register a handler for a known catalog add-on.

    Registration does not enable the add-on. Duplicate registrations are
    rejected so development reloads do not accidentally execute work twice.
    """
    slug = addon.strip().lower()
    if get_addon(slug) is None:
        raise ValueError(f"cannot register hook for unknown add-on {addon!r}")
    registration = HookRegistration(addon=slug, point=point, handler=handler)
    if registration in _HOOKS:
        raise ValueError(f"duplicate add-on hook: {slug}/{point.value}")
    _HOOKS.append(registration)


def run_hooks(point: HookPoint, context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Run enabled handlers and isolate each optional integration's failure."""
    results: list[dict[str, Any]] = []
    for registration in tuple(_HOOKS):
        if registration.point is not point or not addon_enabled(registration.addon):
            continue
        try:
            value = registration.handler(context)
            results.append({"addon": registration.addon, "ok": True, "result": dict(value or {})})
        except Exception as exc:  # add-ons must not break the engine path
            results.append({"addon": registration.addon, "ok": False, "error": str(exc)})
    return results


@task(name="addons-run-hooks")
def run_hooks_task(point: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefect integration point for registered add-on lifecycle handlers."""
    return run_hooks(HookPoint(point), context)


def clear_hooks() -> None:
    """Clear registrations (primarily for isolated tests)."""
    _HOOKS.clear()
