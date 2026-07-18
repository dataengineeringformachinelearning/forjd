"""Request bodies for unified /api/v1/ml routes."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class MlFitRequest(BaseModel):
    tenant_id: UUID | None = None
    # Tabular
    features: list[list[float]] | None = None
    labels: list[int] | None = None
    # Series / text
    series: list[float] | None = None
    texts: list[str] | None = None
    # Hyperparams
    epochs: int = Field(default=12, ge=1, le=200)
    seq_len: int = Field(default=16, ge=4, le=256)
    horizon: int = Field(default=4, ge=1, le=64)
    contamination: float = Field(default=0.1, ge=0.01, le=0.5)


class MlScoreRequest(BaseModel):
    tenant_id: UUID | None = None
    features: list[list[float]] | None = None
    series: list[float] | None = None
    texts: list[str] | None = None
    # forecasting model pick / embedding backend
    model: str | None = None
    backend: str | None = None
    threshold: float | None = None
