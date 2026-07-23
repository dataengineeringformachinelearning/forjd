"""Shared FastAPI dependencies for the v1 API surface.

Keeps pool/cursor helpers consistent across ingest, projections, replay, and
sessions so partner BFFs (e.g. DEML) see one error shape for unavailable DB
and invalid ISO cursors.
"""

from __future__ import annotations

from datetime import datetime

import asyncpg
from fastapi import HTTPException, Request, status


# --- Database pool (fail closed when lifespan soft-connect failed) ---
def require_db_pool(request: Request) -> asyncpg.Pool:
    """Return the app Postgres pool or raise 503 for partner-visible probes."""
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return pool


# --- Live/projection ISO cursor ---
def parse_iso_cursor(value: str | None) -> datetime | None:
    """Parse an ISO-8601 ``since`` cursor; reject malformed values with 400."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="since must be an ISO-8601 timestamp",
        ) from exc
