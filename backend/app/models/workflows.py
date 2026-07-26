"""Pydantic response contracts for the workflow catalog API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# --- Visual pipeline step (BFF / Account UX; YAML step id remains SoT) ---
class PipelineStepCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    detail: str = ""
    kind: Literal["process", "detect", "unknown"] = "unknown"


# --- Catalog row (no secrets; YAML-driven config surface) ---
class WorkflowSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    version: int = 1
    enabled: bool = True
    default: bool = False
    content_types: list[str] = Field(default_factory=list)
    event_types: list[str] = Field(default_factory=list)
    catalog_event_types: list[dict[str, Any]] = Field(default_factory=list)
    aliases: dict[str, Any] = Field(default_factory=dict)
    processor: str = "sealed_metadata"
    steps: list[str] = Field(default_factory=list)
    pipeline_steps: list[PipelineStepCard] = Field(default_factory=list)
    size_anomaly: dict[str, Any] = Field(default_factory=dict)
    rate_anomaly: dict[str, Any] = Field(default_factory=dict)
    projection: dict[str, Any] = Field(default_factory=dict)
    encryption: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    count: int = Field(ge=0)
    workflows: list[WorkflowSummary]
