"""Pydantic schemas for the unsupervised anomaly PoC."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnomalyFitRequest(BaseModel):
    """Train (or retrain) the LSTM-AE on provided windows, or synthetic normals."""

    series_id: str = Field(default="default", max_length=128)
    # Flat series — sliced into overlapping windows of ML_SEQ_LEN.
    values: list[float] | None = Field(default=None, max_length=4096)
    # Or explicit windows (each length == seq_len after pad/truncate).
    windows: list[list[float]] | None = Field(default=None, max_length=512)
    epochs: int | None = Field(default=None, ge=1, le=200)
    use_synthetic: bool = True


class AnomalyScoreRequest(BaseModel):
    """Score one window and optionally persist its latent embedding to pgvector."""

    values: list[float] = Field(..., min_length=1, max_length=256)
    series_id: str = Field(default="default", max_length=128)
    persist: bool = True
    neighbors: int = Field(default=3, ge=0, le=20)


class AnomalyNeighbor(BaseModel):
    id: str
    series_id: str
    reconstruction_error: float
    is_anomaly: bool
    distance: float


class AnomalyScoreResponse(BaseModel):
    ok: bool
    model_version: str
    series_id: str
    reconstruction_error: float
    threshold: float
    is_anomaly: bool
    embedding: list[float]
    embedding_id: str | None = None
    neighbors: list[AnomalyNeighbor] = Field(default_factory=list)
    layers: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
