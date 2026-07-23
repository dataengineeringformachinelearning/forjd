"""Universal E2EE ingestion API — user/service principal + ciphertext-only.

Accepts enterprise Supabase user JWTs and tenant-scoped service tokens.
Server never sees plaintext payloads.

Subprocessor call pattern
-------------------------
Partner SaaS backends keep their own end-user auth. Against FORJD they use only
a tenant-bound Bearer token:

  Authorization: Bearer fjsvc_<prefix>_<secret>
  POST /api/v1/ingest          — sealed AES-256-GCM envelope + tenant_id
  GET  /api/v1/ingest/results  — scores/rollups (optional since=/after_id=)
  GET  /api/v1/projections     — durable projection feed (preferred)

Never forward partner end-user tokens to FORJD.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import AuthUser, get_current_user
from app.core.deps import parse_iso_cursor, require_db_pool
from app.core.ingest_limits import MAX_INGEST_BATCH_EVENTS, MAX_INGEST_BODY_BYTES
from app.models.ingest import EmbeddingIngestRequest, IngestBatchRequest, IngestEventRequest
from app.services import ingest as ingest_svc
from app.services import ingest_processing as processing_svc

router = APIRouter(prefix="/ingest", tags=["ingest"])

_BODY_LIMIT_RESPONSES = {
    status.HTTP_413_CONTENT_TOO_LARGE: {
        "description": f"Ingest JSON body exceeds {MAX_INGEST_BODY_BYTES} bytes."
    }
}


# --- Primary ingest (POST /api/v1/ingest) ---
@router.post(
    "",
    responses=_BODY_LIMIT_RESPONSES,
    summary="Ingest one sealed event",
)
@router.post(
    "/",
    responses=_BODY_LIMIT_RESPONSES,
    summary="Ingest one sealed event",
    include_in_schema=False,
)
async def ingest_root(
    request: Request,
    body: IngestEventRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Ingest one sealed event (any SaaS use case). Canonical path."""
    return await _ingest_one(request, body, user)


# --- Sealed telemetry events (aliases under /events) ---
@router.post(
    "/events",
    responses=_BODY_LIMIT_RESPONSES,
    summary="Ingest one sealed event (alias)",
)
async def ingest_event(
    request: Request,
    body: IngestEventRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Alias of POST /ingest — one sealed event."""
    return await _ingest_one(request, body, user)


@router.post(
    "/events:batch",
    responses=_BODY_LIMIT_RESPONSES,
    summary="Ingest a bounded sealed event batch",
    description=(
        f"Ingest up to {MAX_INGEST_BATCH_EVENTS} sealed events within the shared "
        f"{MAX_INGEST_BODY_BYTES}-byte request cap. Ciphertext only."
    ),
)
async def ingest_events_batch(
    request: Request,
    body: IngestBatchRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Bounded sealed batch ingest. Server stores ciphertext only."""
    pool = require_db_pool(request)
    try:
        return await ingest_svc.ingest_events(pool=pool, user=user, batch=body)
    except ingest_svc.IngestConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/processing/{batch_id}",
    summary="Get durable ingest processing receipt",
)
async def get_processing_status(
    request: Request,
    batch_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a tenant-authorized durable processing receipt (metadata only)."""
    pool = require_db_pool(request)
    try:
        return await processing_svc.get_processing_batch_status(
            pool,
            user=user,
            batch_id=batch_id,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/events",
    summary="List recent sealed event metadata",
)
async def list_events(
    request: Request,
    tenant_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List recent events for a tenant (metadata only — no ciphertext bodies)."""
    pool = require_db_pool(request)
    rows = await ingest_svc.list_recent_events(pool, user=user, tenant_id=tenant_id, limit=limit)
    return {"ok": True, "tenant_id": str(tenant_id), "events": rows}


# --- Stream results (Pathway/Rust scores; no ciphertext) ---
@router.get(
    "/results",
    summary="List stream_results for a tenant",
)
async def list_results(
    request: Request,
    tenant_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    anomalies_only: bool = False,
    workflow_id: str | None = None,
    since: str | None = Query(
        default=None,
        description="ISO-8601 cursor — return rows with created_at > since (ascending)",
    ),
    after_id: UUID | None = Query(
        default=None,
        description="Keyset cursor — return rows after this stream_results.id",
    ),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List Pathway/Prefect/Rust stream_results for a tenant (any SaaS consumer)."""
    pool = require_db_pool(request)
    rows = await ingest_svc.list_stream_results(
        pool,
        user=user,
        tenant_id=tenant_id,
        limit=limit,
        anomalies_only=anomalies_only,
        workflow_id=workflow_id,
        since=parse_iso_cursor(since),
        after_id=after_id,
    )
    return {"ok": True, "tenant_id": str(tenant_id), "results": rows}


# --- Tenant-scoped anomaly embeddings (optional sealed context) ---
@router.post(
    "/embeddings",
    responses=_BODY_LIMIT_RESPONSES,
    summary="Store a tenant-scoped anomaly embedding",
)
async def ingest_embedding(
    request: Request,
    body: EmbeddingIngestRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Store a tenant-scoped anomaly embedding (optional sealed context)."""
    pool = require_db_pool(request)
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
    pool = require_db_pool(request)
    try:
        return await ingest_svc.ingest_events(
            pool=pool,
            user=user,
            batch=IngestBatchRequest(events=[body]),
        )
    except ingest_svc.IngestConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
