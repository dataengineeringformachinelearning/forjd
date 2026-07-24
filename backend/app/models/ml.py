"""Request bodies for unified /api/v1/ml routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
FeatureRow = Annotated[list[FiniteFloat], Field(min_length=1, max_length=64)]
FeatureMatrix = Annotated[list[FeatureRow], Field(min_length=1, max_length=2048)]
Series = Annotated[list[FiniteFloat], Field(min_length=1, max_length=4096)]
Labels = Annotated[
    list[Annotated[int, Field(ge=0, le=1)]],
    Field(min_length=1, max_length=2048),
]
Texts = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=4096)]],
    Field(min_length=1, max_length=128),
]


class MlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MlFitRequest(MlRequest):
    tenant_id: UUID
    # Tabular
    features: FeatureMatrix | None = None
    labels: Labels | None = None
    # Series / text
    series: Series | None = None
    texts: Texts | None = None
    # Hyperparams
    epochs: int = Field(default=12, ge=1, le=200)
    seq_len: int = Field(default=16, ge=4, le=256)
    horizon: int = Field(default=4, ge=1, le=64)
    contamination: float = Field(default=0.1, ge=0.01, le=0.5)


class MlScoreRequest(MlRequest):
    tenant_id: UUID
    features: FeatureMatrix | None = None
    series: Series | None = None
    texts: Texts | None = None
    # forecasting model pick / embedding backend
    model: str | None = Field(default=None, min_length=1, max_length=64)
    backend: str | None = Field(default=None, min_length=1, max_length=64)
    threshold: FiniteFloat | None = Field(default=None, ge=0.0)
