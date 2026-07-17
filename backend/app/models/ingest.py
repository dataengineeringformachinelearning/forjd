"""Pydantic contracts for universal E2EE event ingestion (any SaaS use case)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.crypto import ALGO_AES_256_GCM, SealedEnvelope


# --- Encryption options (server validates policy; never opens ciphertext) ---
class EncryptionOptions(BaseModel):
    """Client-declared encryption mode. Only E2EE is accepted on this path today."""

    mode: Literal["e2ee"] = "e2ee"
    algo: Literal["aes-256-gcm"] = "aes-256-gcm"


# --- Wire envelope (server validates shape; never opens ciphertext) ---
class EncryptedEnvelope(BaseModel):
    """Client-sealed AES-256-GCM envelope (server never opens this on the E2EE path)."""

    algo: str = Field(default=ALGO_AES_256_GCM, max_length=32)
    key_id: str = Field(..., min_length=1, max_length=256)
    nonce: str = Field(..., min_length=8, max_length=64, description="base64 12-byte nonce")
    ciphertext: str = Field(..., min_length=24, max_length=1_048_576, description="base64")
    ratchet_header: str | None = Field(
        default=None,
        max_length=8192,
        description="Opaque Double Ratchet header (base64); server must not parse",
    )
    ciphertext_sha256: str = Field(..., min_length=64, max_length=64)

    def to_sealed(self) -> SealedEnvelope:
        env = SealedEnvelope(
            algo=self.algo,
            key_id=self.key_id,
            nonce=self.nonce,
            ciphertext=self.ciphertext,
            ratchet_header=self.ratchet_header,
            ciphertext_sha256=self.ciphertext_sha256,
        )
        env.validate_sizes()
        return env


# --- Ingest request / response (use-case agnostic) ---
class IngestEventRequest(BaseModel):
    """Generic sealed event for any tenant / product use case."""

    tenant_id: UUID
    client_event_id: str = Field(..., min_length=1, max_length=128)
    occurred_at: datetime | None = None
    # Primary routing key → workflow registry (see backend/workflows/).
    content_type: str = Field(default="application/forjd-event+v1", max_length=128)
    # Optional finer routing inside a content_type (e.g. deml.metric, iot.sample).
    event_type: str | None = Field(default=None, max_length=128)
    schema_version: int = Field(default=1, ge=1, le=1000)
    # Optional explicit workflow override; else resolved from content_type/event_type.
    workflow_id: str | None = Field(default=None, max_length=128)
    encryption: EncryptionOptions = Field(default_factory=EncryptionOptions)
    envelope: EncryptedEnvelope
    # Non-sensitive routing tags only (never put plaintext payloads here).
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content_type", "event_type", "workflow_id")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("metadata")
    @classmethod
    def _metadata_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(str(value)) > 4096:
            raise ValueError("metadata too large")
        return value


class IngestBatchRequest(BaseModel):
    events: list[IngestEventRequest] = Field(..., min_length=1, max_length=100)


class IngestEventResult(BaseModel):
    id: UUID
    tenant_id: UUID
    client_event_id: str
    created_at: datetime
    duplicate: bool = False
    workflow_id: str | None = None


class IngestResponse(BaseModel):
    ok: bool
    accepted: int
    results: list[IngestEventResult]
    prefect: dict[str, Any] | None = None


# --- Optional anomaly embedding alongside a sealed event ---
class EmbeddingIngestRequest(BaseModel):
    """Tenant-scoped vector (ML features / threat scores); optional sealed context."""

    tenant_id: UUID
    telemetry_event_id: UUID | None = Field(
        default=None,
        description="FK to sealed event id (column name historical; any use case)",
    )
    series_id: str = Field(default="default", max_length=128)
    model_version: str = Field(..., min_length=1, max_length=64)
    embedding: list[float] | None = Field(default=None, max_length=64)
    reconstruction_error: float | None = None
    is_anomaly: bool = False
    context_ciphertext: str | None = Field(default=None, max_length=1_048_576)
    context_nonce: str | None = Field(default=None, max_length=64)
    context_key_id: str | None = Field(default=None, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)
