"""Add-on catalog API — inspect which optional integrations are enabled.

Read-only and unauthenticated: it exposes capability metadata only (never
secrets), so operators and the frontend can see what is wired on a deployment.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.addons import ADDONS, addon_enabled, get_addon

router = APIRouter(prefix="/addons", tags=["addons"])


def _serialize(slug: str) -> dict[str, Any]:
    addon = get_addon(slug)
    if addon is None:  # pragma: no cover - guarded by callers
        raise HTTPException(status_code=404, detail=f"unknown add-on {slug!r}")
    enabled = addon_enabled(addon.slug)
    return {
        "slug": addon.slug,
        "name": addon.name,
        "category": addon.category.value,
        "kind": addon.kind.value,
        "summary": addon.summary,
        "source_url": addon.source_url,
        "dependency_group": addon.dependency_group,
        "tags": list(addon.tags),
        "enabled": enabled,
        # Only meaningful once enabled; still cheap to report.
        "available": addon.available(),
    }


@router.get("")
async def list_addons() -> dict[str, Any]:
    items = [_serialize(a.slug) for a in ADDONS]
    return {
        "count": len(items),
        "enabled_count": sum(1 for i in items if i["enabled"]),
        "addons": items,
    }


@router.get("/{slug}")
async def get_addon_detail(slug: str) -> dict[str, Any]:
    return _serialize(slug)
