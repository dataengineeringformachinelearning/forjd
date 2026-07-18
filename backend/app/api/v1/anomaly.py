"""Unsupervised anomaly API — LSTM-AE + Supabase pgvector (dev / staging only).

Auth required. Rows are global (no tenant_id) and may persist plaintext series
windows — never expose in production. Prefer tenant-scoped ``/api/v1/ml/*``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.auth import AuthUser, get_current_user
from app.core.config import settings
from app.models.anomaly import AnomalyFitRequest, AnomalyScoreRequest
from app.services import anomaly as anomaly_svc

router = APIRouter(prefix="/anomaly", tags=["anomaly"])


# --- Production gate (global embeddings are not tenant-safe) ---
def _reject_in_production() -> None:
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="not found",
        )


@router.get("")
async def get_anomaly(
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Model status + recent pgvector rows (non-production operators only)."""
    _reject_in_production()
    del user
    pool = getattr(request.app.state, "db_pool", None)
    return {
        "ml": anomaly_svc.ml_status(),
        "recent": await anomaly_svc.recent_embeddings(pool, limit=10),
    }


@router.post("/fit")
async def fit_anomaly(
    request: Request,
    body: AnomalyFitRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Train the LSTM-AE (synthetic normals by default) and ensure pgvector tables."""
    _reject_in_production()
    del user
    return await anomaly_svc.fit_anomaly(
        pool=getattr(request.app.state, "db_pool", None),
        series_id=body.series_id,
        values=body.values,
        windows=body.windows,
        epochs=body.epochs,
        use_synthetic=body.use_synthetic,
    )


@router.post("/score")
async def score_anomaly(
    request: Request,
    body: AnomalyScoreRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Score a window, persist latent embedding, return nearest neighbors."""
    _reject_in_production()
    del user
    return await anomaly_svc.score_anomaly(
        pool=getattr(request.app.state, "db_pool", None),
        values=body.values,
        series_id=body.series_id,
        persist=body.persist,
        neighbors=body.neighbors,
    )
