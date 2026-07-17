"""Secure E2EE ingestion API — Supabase JWT + ciphertext-only persistence."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.ingest import EmbeddingIngestRequest, IngestBatchRequest, IngestEventRequest
from app.services import ingest as ingest_svc

router = APIRouter(prefix="/ingest", tags=["ingest"])


# --- Sealed telemetry events ---
@router.post("/events")
async def ingest_event(
    request: Request,
    body: IngestEventRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Ingest one AES-256-GCM sealed telemetry event (E2EE)."""
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
