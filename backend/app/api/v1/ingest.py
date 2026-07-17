"""Universal E2EE ingestion API — user/service principal + ciphertext-only.

Accepts enterprise Supabase user JWTs and tenant-scoped service tokens
(subprocessors such as DEML). Server never sees plaintext payloads.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.ingest import EmbeddingIngestRequest, IngestBatchRequest, IngestEventRequest
from app.services import ingest as ingest_svc

router = APIRouter(prefix="/ingest", tags=["ingest"])


# --- Primary ingest (POST /api/v1/ingest) ---
@router.post("")
@router.post("/")
async def ingest_root(
    request: Request,
    body: IngestEventRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Ingest one sealed event (any SaaS use case). Canonical path."""
    return await _ingest_one(request, body, user)


# --- Sealed telemetry events (aliases under /events) ---
@router.post("/events")
async def ingest_event(
    request: Request,
    body: IngestEventRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Alias of POST /ingest — one sealed event."""
    return await _ingest_one(request, body, user)


@router.post("/events:batch")
async def ingest_events_batch(
    request: Request,
    body: IngestBatchRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Batch ingest (max 100). Server stores ciphertext only."""
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        return await ingest_svc.ingest_events(pool=pool, user=user, batch=body)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/events")
async def list_events(
    request: Request,
    tenant_id: UUID,
    limit: int = 20,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List recent events for a tenant (metadata only — no ciphertext bodies)."""
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    limit = max(1, min(limit, 100))
    rows = await ingest_svc.list_recent_events(
        pool, user=user, tenant_id=tenant_id, limit=limit
    )
    return {"ok": True, "tenant_id": str(tenant_id), "events": rows}


# --- Stream results (Pathway scores/rollups; no ciphertext) ---
@router.get("/results")
async def list_results(
    request: Request,
    tenant_id: UUID,
    limit: int = 20,
    anomalies_only: bool = False,
    workflow_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List Pathway/Prefect stream_results for a tenant (any SaaS consumer)."""
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    limit = max(1, min(limit, 100))
    rows = await ingest_svc.list_stream_results(
        pool,
        user=user,
        tenant_id=tenant_id,
        limit=limit,
        anomalies_only=anomalies_only,
        workflow_id=workflow_id,
    )
    return {"ok": True, "tenant_id": str(tenant_id), "results": rows}


# --- Tenant-scoped anomaly embeddings (optional sealed context) ---
@router.post("/embeddings")
async def ingest_embedding(
    request: Request,
    body: EmbeddingIngestRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Store a tenant-scoped anomaly embedding (optional sealed context)."""
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        return await ingest_svc.ingest_embedding(pool=pool, user=user, body=body)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --- Shared single-event path ---
async def _ingest_one(
    request: Request,
    body: IngestEventRequest,
    user: AuthUser,
) -> dict[str, Any]:
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    try:
        return await ingest_svc.ingest_events(
            pool=pool,
            user=user,
            batch=IngestBatchRequest(events=[body]),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
