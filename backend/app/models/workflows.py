"""Pydantic response contracts for the workflow catalog API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    projection: dict[str, Any] = Field(default_factory=dict)
    encryption: dict[str, Any] = Field(default_factory=dict)


class WorkflowListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    count: int = Field(ge=0)
    workflows: list[WorkflowSummary]
