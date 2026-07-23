"""Workflow catalog API — list configured use cases (YAML/JSON driven)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import AuthUser, get_current_user
from app.models.workflows import WorkflowListResponse, WorkflowSummary
from app.workflows.registry import list_workflow_summaries

router = APIRouter(prefix="/workflows", tags=["workflows"])


# --- List registered workflows (no secrets; config surface for clients) ---
@router.get(
    "",
    response_model=WorkflowListResponse,
    summary="List sealed-stream workflow definitions",
    response_description="Enabled workflow summaries from backend/workflows/",
)
async def list_workflows(
    _user: AuthUser = Depends(get_current_user),
) -> WorkflowListResponse:
    """Return enabled workflow summaries for partner BFFs (auth required)."""
    items = list_workflow_summaries()
    return WorkflowListResponse(
        ok=True,
        count=len(items),
        workflows=[WorkflowSummary.model_validate(item) for item in items],
    )
