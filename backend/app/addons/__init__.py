"""FORJD add-on registry.

Add-ons are optional, config-gated integrations. Every add-on is **disabled by
default**; a deployment enables the ones it needs via ``FORJD_ADDONS`` (or
``FORJD_ADDONS=all``). Partner control planes (e.g. DEML) enable the full set
through their environment configuration.

Public surface:
    - ``ADDONS``           — immutable catalog of every registered add-on.
    - ``enabled_addons()`` — the subset enabled by the current settings.
    - ``get_addon(slug)``  — one descriptor by slug.
    - ``addon_enabled(slug)`` — bool gate for callers.
"""

from __future__ import annotations

from app.addons.hooks import HookPoint, register_hook, run_hooks
from app.addons.registry import (
    ADDONS,
    Addon,
    AddonCategory,
    AddonKind,
    addon_enabled,
    enabled_addons,
    get_addon,
)

__all__ = [
    "ADDONS",
    "Addon",
    "AddonCategory",
    "AddonKind",
    "addon_enabled",
    "enabled_addons",
    "get_addon",
    "HookPoint",
    "register_hook",
    "run_hooks",
]
