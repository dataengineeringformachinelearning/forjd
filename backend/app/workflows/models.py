"""Pydantic schema for YAML/JSON workflow definitions (use-case config)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# --- Match rules (content_type / event_type → this workflow) ---
class WorkflowMatch(BaseModel):
    content_types: list[str] = Field(default_factory=list)
    event_types: list[str] = Field(
        default_factory=list,
        description="Empty = match any event_type for the content_types",
    )


# --- Detector params (pluggable; see app.workflows.detectors) ---
class SizeAnomalyParams(BaseModel):
    zscore: float = 2.5
    max_cipher_len: int = 262_144


class RateAnomalyParams(BaseModel):
    max_events: int = 500
    window_sec: int = 60  # reserved for continuous projector windows


class PipelineConfig(BaseModel):
    """Declares which registered processor runs and which steps it enables."""

    processor: str = Field(
        default="sealed_metadata",
        description="Key in app.workflows.processors.REGISTRY",
    )
    steps: list[Literal["rollup", "size_anomaly", "rate_anomaly"]] = Field(
        default_factory=lambda: ["rollup", "size_anomaly"]
    )
    size_anomaly: SizeAnomalyParams = Field(default_factory=SizeAnomalyParams)
    rate_anomaly: RateAnomalyParams = Field(default_factory=RateAnomalyParams)
    # Durable projection name stamped onto stream_results.
    projection_name: str = Field(default="sealed.default", max_length=128)


class WorkflowOutputs(BaseModel):
    table: str = "stream_results"
    tags: dict[str, Any] = Field(default_factory=dict)


class EncryptionPolicy(BaseModel):
    """Server-enforced encryption policy for this use case (fail closed)."""

    modes: list[Literal["e2ee"]] = Field(default_factory=lambda: ["e2ee"])
    algos: list[str] = Field(default_factory=lambda: ["aes-256-gcm"])


# --- Top-level workflow document ---
class WorkflowDefinition(BaseModel):
    id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    name: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    version: int = Field(default=1, ge=1)
    enabled: bool = True
    default: bool = False
    match: WorkflowMatch = Field(default_factory=WorkflowMatch)
    encryption: EncryptionPolicy = Field(default_factory=EncryptionPolicy)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    outputs: WorkflowOutputs = Field(default_factory=WorkflowOutputs)

    @field_validator("id")
    @classmethod
    def _lower_id(cls, value: str) -> str:
        return value.strip().lower()
