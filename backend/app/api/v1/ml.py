"""Unified ML catalog backed by Supabase (Auth + Postgres + pgvector + Realtime).

GET  /api/v1/ml/models
GET  /api/v1/ml/scores?tenant_id=
POST /api/v1/ml/{model_id}/fit
POST /api/v1/ml/{model_id}/score

Security: JWT/service principal + tenant check. Persist metrics/latents/scores
only — never sealed ciphertext. When ``tenant_id`` is set and Postgres is up,
fit/score hydrate from ``stream_results`` metadata and write
``training_runs`` / ``embedding_vectors`` / ``ml_scores``.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import AuthUser, get_current_user, pool_from_request
from app.models.ml import MlFitRequest, MlScoreRequest
from app.services import tenants as tenant_svc
from app.services.ml import registry as ml_registry
from app.services.ml import store as ml_store
from app.services.ml import supabase_bridge as ml_sb

router = APIRouter(prefix="/ml", tags=["ml"])

_FIT_INPUTS: dict[str, tuple[str, ...]] = {
    "lstm_autoencoder": ("series",),
    "classical_anomaly": ("features",),
    "threat_ensemble": ("features", "labels"),
    "transformer_anomaly": ("series",),
    "forecasting": ("series",),
    "embeddings": ("texts",),
    "norse_ssn": ("series",),
}
_SCORE_INPUTS: dict[str, tuple[str, ...]] = {
    "lstm_autoencoder": ("series",),
    "classical_anomaly": ("features",),
    "threat_ensemble": ("features",),
    "transformer_anomaly": ("series",),
    "forecasting": ("series",),
    "embeddings": ("texts",),
    "norse_ssn": ("series",),
}


# --- Tenant gate (required for Supabase-backed path) ---
async def _require_tenant(
    request: Request,
    user: AuthUser,
    tenant_id: UUID | None,
    *,
    write: bool,
) -> None:
    required_scope = frozenset({"ml:write" if write else "ml:read"})
    if tenant_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="tenant_id is required for ML fit and score",
        )
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    roles = (
        frozenset({"owner", "admin"})
        if write
        else frozenset({"owner", "admin", "member", "viewer"})
    )
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=roles,
        required_scopes=required_scope,
    )


def _require_catalog_scope(user: AuthUser) -> None:
    """Keep the global model catalog readable to humans but scoped for M2M."""
    if user.is_service and "*" not in user.scopes and "ml:read" not in user.scopes:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="insufficient service scope",
        )


def _require_tenant_inputs(
    model_id: str,
    kwargs: dict[str, Any],
    *,
    fit: bool,
) -> None:
    """Tenant-persisted runs must never silently train or score fixture data."""
    if not kwargs.get("tenant_id"):
        return
    required = (_FIT_INPUTS if fit else _SCORE_INPUTS).get(model_id, ())
    missing = [key for key in required if not kwargs.get(key)]
    if missing:
        action = "fit" if fit else "score"
        names = ", ".join(missing)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"real tenant {names} required for {model_id} {action}",
        )


# --- Catalog ---
@router.get("/models")
async def list_ml_models(
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _require_catalog_scope(user)
    return {
        "ok": True,
        "models": ml_registry.list_models(),
        "supabase": {
            "tables": ["training_runs", "embedding_vectors", "ml_scores"],
            "note": "tenant_id and real tenant inputs are required on fit/score",
        },
    }


# --- Recent scores (Realtime-friendly polling) ---
@router.get("/scores")
async def list_ml_scores(
    request: Request,
    tenant_id: UUID,
    family: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    await _require_tenant(request, user, tenant_id, write=False)
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    rows = await ml_store.list_recent_scores(pool, tenant_id=tenant_id, family=family, limit=limit)
    return {"ok": True, "tenant_id": str(tenant_id), "scores": rows}


@router.get("/benchmark")
async def ml_benchmark(
    request: Request,
    tenant_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Self-benchmark summary from recent ``training_runs`` (partner dashboards)."""
    await _require_tenant(request, user, tenant_id, write=False)
    pool = pool_from_request(request)
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    runs = await ml_store.list_recent_training_runs(pool, tenant_id=tenant_id, limit=40)
    scope = ml_store.benchmark_from_training_runs(runs)
    return {
        "ok": True,
        "tenant_id": str(tenant_id),
        "benchmarking": {"current_scope": scope, "platform_reference": None},
        "runs": runs[:10],
    }


# --- Fit ---
@router.post("/{model_id}/fit")
async def fit_ml_model(
    model_id: str,
    request: Request,
    body: MlFitRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    await _require_tenant(request, user, body.tenant_id, write=True)
    pool = pool_from_request(request)
    kwargs: dict[str, Any] = {
        "epochs": body.epochs,
        "seq_len": body.seq_len,
        "horizon": body.horizon,
        "contamination": body.contamination,
        "tenant_id": str(body.tenant_id) if body.tenant_id else None,
    }
    if body.features is not None:
        kwargs["features"] = body.features
    if body.labels is not None:
        kwargs["labels"] = body.labels
    if body.series is not None:
        kwargs["series"] = body.series
    if body.texts is not None:
        kwargs["texts"] = body.texts

    kwargs = await ml_sb.hydrate_fit_kwargs(pool, model_id, kwargs)
    _require_tenant_inputs(model_id, kwargs, fit=True)
    try:
        result = await asyncio.to_thread(
            ml_registry.fit_model,
            model_id,
            **_filter_kwargs(model_id, kwargs, fit=True),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return await ml_sb.persist_fit(
        pool,
        model_id=model_id,
        tenant_id=str(body.tenant_id) if body.tenant_id else None,
        result=result,
    )


# --- Score / encode ---
@router.post("/{model_id}/score")
async def score_ml_model(
    model_id: str,
    request: Request,
    body: MlScoreRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    await _require_tenant(request, user, body.tenant_id, write=True)
    pool = pool_from_request(request)
    kwargs: dict[str, Any] = {
        "tenant_id": str(body.tenant_id) if body.tenant_id else None,
    }
    if body.features is not None:
        kwargs["features"] = body.features
    if body.series is not None:
        kwargs["series"] = body.series
    if body.texts is not None:
        kwargs["texts"] = body.texts
    if body.model is not None:
        kwargs["model"] = body.model
    if body.backend is not None:
        kwargs["backend"] = body.backend
    if body.threshold is not None:
        kwargs["threshold"] = body.threshold

    # Score-side hydrate: if no features/series, pull latest metadata series.
    if pool and body.tenant_id:
        if model_id in {"classical_anomaly", "threat_ensemble"} and not kwargs.get("features"):
            feats = await ml_store.features_from_stream_results(
                pool, tenant_id=str(body.tenant_id), limit=32
            )
            if feats:
                kwargs["features"] = feats[:1]  # query is newest-first
        if model_id in {
            "lstm_autoencoder",
            "transformer_anomaly",
            "forecasting",
            "norse_ssn",
        } and not kwargs.get("series"):
            series = await ml_store.series_from_stream_results(pool, tenant_id=str(body.tenant_id))
            if series:
                kwargs["series"] = series

    _require_tenant_inputs(model_id, kwargs, fit=False)
    try:
        result = await asyncio.to_thread(
            ml_registry.score_model,
            model_id,
            **_filter_kwargs(model_id, kwargs, fit=False),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return await ml_sb.persist_score(
        pool,
        model_id=model_id,
        tenant_id=str(body.tenant_id) if body.tenant_id else None,
        result=result,
    )


# --- Kwarg allow-lists per family ---
_FIT_KEYS: dict[str, frozenset[str]] = {
    "lstm_autoencoder": frozenset({"series", "seq_len", "epochs", "tenant_id"}),
    "classical_anomaly": frozenset({"features", "tenant_id", "contamination"}),
    "threat_ensemble": frozenset({"features", "labels", "tenant_id"}),
    "transformer_anomaly": frozenset({"series", "seq_len", "epochs", "tenant_id"}),
    "forecasting": frozenset({"series", "seq_len", "horizon", "epochs", "tenant_id"}),
    "embeddings": frozenset({"texts", "epochs", "tenant_id"}),
    "norse_ssn": frozenset({"series", "seq_len", "epochs", "tenant_id"}),
}
_SCORE_KEYS: dict[str, frozenset[str]] = {
    "lstm_autoencoder": frozenset({"series", "tenant_id"}),
    "classical_anomaly": frozenset({"features", "tenant_id"}),
    "threat_ensemble": frozenset({"features", "tenant_id"}),
    "transformer_anomaly": frozenset({"series", "tenant_id", "threshold"}),
    "forecasting": frozenset({"series", "tenant_id", "model"}),
    "embeddings": frozenset({"texts", "tenant_id", "backend"}),
    "norse_ssn": frozenset({"series", "tenant_id", "threshold"}),
}


def _filter_kwargs(model_id: str, kwargs: dict[str, Any], *, fit: bool) -> dict[str, Any]:
    allow = (_FIT_KEYS if fit else _SCORE_KEYS).get(model_id)
    if allow is None:
        return kwargs
    return {k: v for k, v in kwargs.items() if k in allow and v is not None}
