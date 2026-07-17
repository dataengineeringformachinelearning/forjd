"""Workflow catalog API — list configured use cases (YAML/JSON driven)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.auth import AuthUser, get_current_user
from app.workflows.registry import list_workflow_summaries

router = APIRouter(prefix="/workflows", tags=["workflows"])


# --- List registered workflows (no secrets; config surface for clients) ---
@router.get("")
async def list_workflows(
    _user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return enabled workflow summaries from backend/workflows/."""
    items = list_workflow_summaries()
    return {"ok": True, "count": len(items), "workflows": items}
