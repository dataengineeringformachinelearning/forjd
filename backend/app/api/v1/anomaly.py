"""Unsupervised anomaly API — LSTM-AE + Supabase pgvector."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.models.anomaly import AnomalyFitRequest, AnomalyScoreRequest
from app.services import anomaly as anomaly_svc

router = APIRouter(prefix="/anomaly", tags=["anomaly"])


@router.get("")
async def get_anomaly(request: Request) -> dict[str, Any]:
    """Model status + recent pgvector rows."""
    pool = getattr(request.app.state, "db_pool", None)
    return {
        "ml": anomaly_svc.ml_status(),
        "recent": await anomaly_svc.recent_embeddings(pool, limit=10),
    }


@router.post("/fit")
async def fit_anomaly(request: Request, body: AnomalyFitRequest) -> dict[str, Any]:
    """Train the LSTM-AE (synthetic normals by default) and ensure pgvector tables."""
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
    request: Request, body: AnomalyScoreRequest
) -> dict[str, Any]:
    """Score a window, persist latent embedding, return nearest neighbors."""
    return await anomaly_svc.score_anomaly(
        pool=getattr(request.app.state, "db_pool", None),
        values=body.values,
        series_id=body.series_id,
        persist=body.persist,
        neighbors=body.neighbors,
    )
