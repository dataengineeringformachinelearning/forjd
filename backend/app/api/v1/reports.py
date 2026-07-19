"""Report documents API — durable tenant-scoped partner report storage."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.reports import CreateReportDocumentRequest
from app.services import report_documents as report_docs_svc

router = APIRouter(prefix="/reports", tags=["reports"])


def _pool(request: Request) -> Any:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    return pool


# --- Create a report document ---
@router.post("/documents")
async def create_report_document(
    request: Request,
    body: CreateReportDocumentRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await report_docs_svc.create_document(_pool(request), user=user, document=body)


# --- List report documents ---
@router.get("/documents")
async def list_report_documents(
    request: Request,
    tenant_id: UUID,
    kind: str | None = Query(default=None, max_length=64),
    limit: int = Query(100, ge=1, le=500),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await report_docs_svc.list_documents(
        _pool(request),
        user=user,
        tenant_id=tenant_id,
        kind=kind,
        limit=limit,
    )
