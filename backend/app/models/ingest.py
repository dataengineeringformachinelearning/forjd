"""Pydantic contracts for E2EE telemetry ingestion."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.crypto import ALGO_AES_256_GCM, SealedEnvelope


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


# --- Ingest request / response ---
class IngestEventRequest(BaseModel):
    tenant_id: UUID
    client_event_id: str = Field(..., min_length=1, max_length=128)
    occurred_at: datetime | None = None
    content_type: str = Field(default="application/forjd-telemetry+v1", max_length=128)
    schema_version: int = Field(default=1, ge=1, le=1000)
    envelope: EncryptedEnvelope
    # Non-sensitive routing tags only (never put plaintext telemetry here).
    metadata: dict[str, Any] = Field(default_factory=dict)

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


class IngestResponse(BaseModel):
    ok: bool
    accepted: int
    results: list[IngestEventResult]
    prefect: dict[str, Any] | None = None


# --- Optional anomaly embedding alongside a sealed event ---
class EmbeddingIngestRequest(BaseModel):
    """Optional tenant-scoped anomaly vector (often paired with a sealed event)."""

    tenant_id: UUID
    telemetry_event_id: UUID | None = None
    series_id: str = Field(default="default", max_length=128)
    model_version: str = Field(..., min_length=1, max_length=64)
    embedding: list[float] | None = Field(default=None, max_length=64)
    reconstruction_error: float | None = None
    is_anomaly: bool = False
    context_ciphertext: str | None = Field(default=None, max_length=1_048_576)
    context_nonce: str | None = Field(default=None, max_length=64)
    context_key_id: str | None = Field(default=None, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)
