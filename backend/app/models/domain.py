"""Pydantic request models for domain APIs."""

from __future__ import annotations

import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.sanitize import sanitize_label, sanitize_text
from app.core.text_fields import (
    Description4k,
    OptionalDescription4k,
    OptionalTitle255,
    Title255,
)
from app.models.siem import validate_signal_metadata


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- Threat intel ---
class ThreatRefreshRequest(_StrictRequest):
    source: Literal["abuse.ch"] = "abuse.ch"


class TaxiiIngestRequest(_StrictRequest):
    collection_url: str = Field(..., min_length=8, max_length=2048)
    source: Title255
    username: str | None = Field(default=None, max_length=256)
    password: str | None = Field(default=None, max_length=512)
    tenant_id: UUID | None = None
    is_platform: bool = False

    @model_validator(mode="after")
    def _scope_shape(self) -> TaxiiIngestRequest:
        if self.is_platform and self.tenant_id is not None:
            raise ValueError("platform TAXII ingest cannot specify tenant_id")
        if not self.is_platform and self.tenant_id is None:
            raise ValueError("tenant_id is required for tenant TAXII ingest")
        if bool(self.username) != bool(self.password):
            raise ValueError("TAXII username and password must be supplied together")
        return self


class CorrelateRequest(_StrictRequest):
    tenant_id: UUID
    context: dict[str, Any] = Field(default_factory=dict)
    run_playbooks: bool = True
    idempotency_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )

    @field_validator("context")
    @classmethod
    def _safe_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_signal_metadata(value)


# --- SOC ---
class CreateCaseRequest(_StrictRequest):
    tenant_id: UUID
    title: Title255
    description: Description4k = ""
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _safe_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_signal_metadata(value)


class UpdateCaseRequest(_StrictRequest):
    tenant_id: UUID
    title: OptionalTitle255 = None
    description: OptionalDescription4k = None
    status: Literal["open", "investigating", "mitigated", "resolved", "false_positive"] | None = (
        None
    )
    severity: Literal["low", "medium", "high", "critical"] | None = None
    assigned_actor_id: UUID | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("metadata")
    @classmethod
    def _safe_patch_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_signal_metadata(value) if value is not None else None

    @model_validator(mode="after")
    def _has_update(self) -> UpdateCaseRequest:
        if not (self.model_fields_set - {"tenant_id"}):
            raise ValueError("at least one case field must be supplied")
        return self


# --- Playbooks ---
class PlaybookActionIn(_StrictRequest):
    action_type: Literal["webhook", "email_alert", "block_ip", "revoke_api_key"]
    configuration: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = Field(default=0, ge=0, le=1000)

    @model_validator(mode="after")
    def _safe_configuration(self) -> PlaybookActionIn:
        allowed = {
            "webhook": {"url", "secret_ref"},
            "email_alert": {"template", "channel_ref"},
            "block_ip": {"provider_ref", "duration_seconds"},
            "revoke_api_key": {"credential_ref"},
        }[self.action_type]
        extra = set(self.configuration) - allowed
        if extra:
            raise ValueError(f"unsupported {self.action_type} configuration keys: {sorted(extra)}")
        if len(str(self.configuration)) > 4096:
            raise ValueError("action configuration is too large")
        cleaned: dict[str, Any] = {}
        for key, value in self.configuration.items():
            if key != "secret_ref" and any(
                part in key.lower() for part in ("password", "secret", "token", "authorization")
            ):
                raise ValueError("inline action credentials are not allowed; use a secret_ref")
            if isinstance(value, str):
                text = sanitize_text(value, max_length=2048, allow_newlines=False)
                cleaned[key] = text
            else:
                cleaned[key] = value
        secret_ref = cleaned.get("secret_ref")
        if secret_ref is not None and (
            not isinstance(secret_ref, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", secret_ref)
        ):
            raise ValueError("webhook secret_ref must be an opaque 1-128 character identifier")
        return self.model_copy(update={"configuration": cleaned})


class CreatePlaybookRequest(_StrictRequest):
    tenant_id: UUID
    name: Title255
    description: Description4k = ""
    trigger_conditions: dict[str, Any] = Field(default_factory=dict)
    actions: list[PlaybookActionIn] = Field(default_factory=list, max_length=50)

    @field_validator("trigger_conditions")
    @classmethod
    def _safe_trigger(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_signal_metadata(value)


class UpdatePlaybookRequest(_StrictRequest):
    tenant_id: UUID
    name: OptionalTitle255 = None
    description: OptionalDescription4k = None
    is_active: bool | None = None
    trigger_conditions: dict[str, Any] | None = None
    actions: list[PlaybookActionIn] | None = Field(default=None, max_length=50)

    @field_validator("trigger_conditions")
    @classmethod
    def _safe_patch_trigger(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_signal_metadata(value) if value is not None else None

    @model_validator(mode="after")
    def _has_update(self) -> UpdatePlaybookRequest:
        if not (self.model_fields_set - {"tenant_id"}):
            raise ValueError("at least one playbook field must be supplied")
        return self


class ExecutePlaybookRequest(_StrictRequest):
    tenant_id: UUID
    idempotency_key: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("context")
    @classmethod
    def _safe_execute_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_signal_metadata(value)


class AcknowledgePlaybookActionRequest(_StrictRequest):
    tenant_id: UUID
    succeeded: bool
    external_reference: str | None = Field(default=None, max_length=255)

    @field_validator("external_reference", mode="before")
    @classmethod
    def _clean_external_reference(cls, value: object) -> str | None:
        if value is None:
            return None
        text = sanitize_label(str(value), max_length=255)
        return text or None

    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _safe_ack_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_signal_metadata(value)


class RetryPlaybookActionRequest(_StrictRequest):
    tenant_id: UUID


# --- Vulnerabilities ---
class UpdateVulnerabilityRequest(_StrictRequest):
    tenant_id: UUID
    asset_id: UUID | None = None
    title: OptionalTitle255 = None
    description: OptionalDescription4k = None
    status: Literal["triage", "open", "in_progress", "resolved", "false_positive"] | None = None
    severity: Literal["low", "medium", "high", "critical"] | None = None
    impact: int | None = Field(default=None, ge=1, le=5)
    likelihood: int | None = Field(default=None, ge=1, le=5)
    cve_id: str | None = Field(default=None, max_length=64)
    telemetry_context: dict[str, Any] | None = None

    @field_validator("telemetry_context")
    @classmethod
    def _safe_telemetry_context(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_signal_metadata(value) if value is not None else None

    @model_validator(mode="after")
    def _has_update(self) -> UpdateVulnerabilityRequest:
        if not (self.model_fields_set - {"tenant_id"}):
            raise ValueError("at least one vulnerability field must be supplied")
        return self


# --- Exports ---
class CreateExportRequest(BaseModel):
    tenant_id: UUID
    idempotency_key: str = Field(..., min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    format: Literal["csv", "json", "parquet", "pdf"] = "csv"
    source_kind: Literal[
        "stream_results", "analytics", "threat", "lighthouse", "vulnerabilities"
    ] = "stream_results"
    limit: int = Field(default=10_000, ge=1, le=100_000)
    days: int = Field(default=7, ge=1, le=90)
    site_url: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def _bounded_pdf_size(self) -> CreateExportRequest:
        if self.format == "pdf":
            if "limit" not in self.__pydantic_fields_set__:
                self.limit = 1_000
            elif self.limit > 1_000:
                raise ValueError("PDF exports support at most 1000 rows")
        return self


# --- Threat ML ---
class ThreatTrainRequest(BaseModel):
    tenant_id: UUID
    epochs: int = Field(default=40, ge=1, le=500)


class ThreatScoreRequest(BaseModel):
    tenant_id: UUID
