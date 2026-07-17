"""Pydantic request models for DEML-extracted domain APIs."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# --- Threat intel ---
class ThreatRefreshRequest(BaseModel):
    source: Literal["abuse.ch"] = "abuse.ch"


class TaxiiIngestRequest(BaseModel):
    collection_url: str = Field(..., min_length=8, max_length=2048)
    source: str = Field(..., min_length=1, max_length=255)
    username: str | None = None
    password: str | None = None
    tenant_id: UUID | None = None
    is_platform: bool = True


class CorrelateRequest(BaseModel):
    tenant_id: UUID
    context: dict[str, Any] = Field(default_factory=dict)
    run_playbooks: bool = True


# --- SOC ---
class CreateCaseRequest(BaseModel):
    tenant_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Playbooks ---
class PlaybookActionIn(BaseModel):
    action_type: Literal["webhook", "email_alert", "block_ip", "revoke_api_key"]
    configuration: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class CreatePlaybookRequest(BaseModel):
    tenant_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    trigger_conditions: dict[str, Any] = Field(default_factory=dict)
    actions: list[PlaybookActionIn] = Field(default_factory=list)


# --- Exports ---
class CreateExportRequest(BaseModel):
    tenant_id: UUID
    format: Literal["csv", "json", "parquet"] = "csv"
    source_kind: str = "stream_results"
    limit: int = Field(default=10_000, ge=1, le=100_000)


# --- Threat ML ---
class ThreatTrainRequest(BaseModel):
    tenant_id: UUID
    epochs: int = Field(default=40, ge=1, le=500)


class ThreatScoreRequest(BaseModel):
    tenant_id: UUID
