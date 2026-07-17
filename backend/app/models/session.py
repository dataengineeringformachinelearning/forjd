"""Pydantic contracts for X25519 crypto session registration (public keys only)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.crypto import CryptoError, validate_x25519_public_b64


# --- Upsert body (public keys only — reject invalid X25519 material) ---
class CryptoSessionUpsert(BaseModel):
    """Register or rotate a device session's public keys for a tenant."""

    tenant_id: UUID
    session_id: str = Field(..., min_length=1, max_length=128)
    identity_public_key: str = Field(
        ...,
        min_length=40,
        max_length=64,
        description="base64 X25519 identity public key (32 bytes)",
    )
    ephemeral_public_key: str | None = Field(
        default=None,
        max_length=64,
        description="base64 X25519 current ratchet public key",
    )
    ratchet_state_hint: str | None = Field(
        default=None,
        max_length=4096,
        description="Opaque client hint; server must not interpret",
    )
    expires_at: datetime | None = None

    @field_validator("identity_public_key")
    @classmethod
    def _identity_pub(cls, value: str) -> str:
        try:
            return validate_x25519_public_b64(value)
        except CryptoError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("ephemeral_public_key")
    @classmethod
    def _ephemeral_pub(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return validate_x25519_public_b64(value)
        except CryptoError as exc:
            raise ValueError(str(exc)) from exc


# --- Response shape ---
class CryptoSessionOut(BaseModel):
    id: UUID
    tenant_id: UUID
    session_id: str
    user_id: UUID
    identity_public_key: str
    ephemeral_public_key: str | None
    ratchet_state_hint: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
