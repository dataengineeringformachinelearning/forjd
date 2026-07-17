"""AES-256-GCM helpers and E2EE envelope contracts for FORJD.

Security model (Signal-inspired, server-minimal knowledge):
  • Clients run Double Ratchet (or equivalent) and derive message keys.
  • Each event is sealed with AES-256-GCM; AAD binds tenant + client_event_id.
  • The API persists ciphertext + opaque ratchet headers — it does **not**
    decrypt E2EE payloads. These helpers exist for:
      1) Client SDKs / tests that share the same envelope format
      2) Optional non-E2EE ops (e.g. local demos) where a key is explicitly supplied

Never put long-term tenant secrets in Settings or the database in plaintext.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

GCM_NONCE_BYTES = 12
AES_KEY_BYTES = 32
ALGO_AES_256_GCM = "aes-256-gcm"


class CryptoError(ValueError):
    """Invalid envelope or cryptographic failure."""


def b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64decode(data: str) -> bytes:
    try:
        return base64.b64decode(data, validate=True)
    except Exception as exc:  # noqa: BLE001 — normalize decode errors
        raise CryptoError("invalid base64") from exc


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def associated_data(*, tenant_id: str, client_event_id: str) -> bytes:
    """AAD binds ciphertext to tenant + idempotency key (prevents cut-and-paste)."""
    return f"{tenant_id}|{client_event_id}".encode()


@dataclass(frozen=True, slots=True)
class SealedEnvelope:
    """Wire format for an E2EE telemetry payload."""

    algo: str
    key_id: str
    nonce: str  # base64
    ciphertext: str  # base64 (ciphertext || tag)
    ratchet_header: str | None
    ciphertext_sha256: str

    def validate_sizes(self) -> None:
        if self.algo != ALGO_AES_256_GCM:
            raise CryptoError(f"unsupported algo: {self.algo}")
        nonce = b64decode(self.nonce)
        if len(nonce) != GCM_NONCE_BYTES:
            raise CryptoError("nonce must be 12 bytes (AES-GCM)")
        ct = b64decode(self.ciphertext)
        # GCM tag is 16 bytes; require some ciphertext body.
        if len(ct) < 17:
            raise CryptoError("ciphertext too short")
        if sha256_hex(ct) != self.ciphertext_sha256.lower():
            raise CryptoError("ciphertext_sha256 mismatch")


def seal(
    plaintext: bytes,
    *,
    key: bytes,
    key_id: str,
    tenant_id: str,
    client_event_id: str,
    ratchet_header: str | None = None,
) -> SealedEnvelope:
    """Encrypt with AES-256-GCM. For client/tests — not used on the E2EE server path."""
    if len(key) != AES_KEY_BYTES:
        raise CryptoError("AES-256 key must be 32 bytes")
    nonce = os.urandom(GCM_NONCE_BYTES)
    aad = associated_data(tenant_id=tenant_id, client_event_id=client_event_id)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return SealedEnvelope(
        algo=ALGO_AES_256_GCM,
        key_id=key_id,
        nonce=b64encode(nonce),
        ciphertext=b64encode(ct),
        ratchet_header=ratchet_header,
        ciphertext_sha256=sha256_hex(ct),
    )


def open_envelope(
    envelope: SealedEnvelope,
    *,
    key: bytes,
    tenant_id: str,
    client_event_id: str,
) -> bytes:
    """Decrypt an envelope. Only for clients / explicit demo keys — never in prod E2EE ingest."""
    envelope.validate_sizes()
    if len(key) != AES_KEY_BYTES:
        raise CryptoError("AES-256 key must be 32 bytes")
    nonce = b64decode(envelope.nonce)
    ct = b64decode(envelope.ciphertext)
    aad = associated_data(tenant_id=tenant_id, client_event_id=client_event_id)
    try:
        return AESGCM(key).decrypt(nonce, ct, aad)
    except Exception as exc:  # noqa: BLE001
        raise CryptoError("decryption failed") from exc
