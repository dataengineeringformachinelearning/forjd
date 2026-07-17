"""AES-256-GCM + X25519 helpers and E2EE envelope contracts for FORJD.

=============================================================================
Security design (Signal-inspired, server-minimal knowledge)
=============================================================================

Threat model
  • FORJD (API + Postgres) must learn as little as possible about telemetry.
  • Plaintext lives only on client devices (or client-held HSMs / secure enclaves).
  • The server persists: ciphertext, GCM nonce, key_id, opaque ratchet headers,
    and non-sensitive routing metadata (tenant_id, timestamps, content_type).

Primitives
  • X25519 ECDH — establish a shared secret between peers / devices.
  • HKDF-SHA256 — expand the ECDH secret into a 32-byte AES key
    (info label binds purpose: "forjd-session-v1").
  • AES-256-GCM — authenticated encryption of each event payload.
    AAD = UTF-8(`${tenant_id}|${client_event_id}`) so ciphertext cannot be
    cut-and-pasted across tenants or idempotency keys.

Forward secrecy (Double Ratchet principles)
  • Clients maintain a Double Ratchet (or equivalent) locally.
  • Each message may advance the DH ratchet (new ephemeral X25519 key pair)
    and always advances the symmetric-key ratchet (new message key).
  • Compromising the current message key does not reveal past plaintext
    (forward secrecy) or future keys if the DH ratchet continues (future secrecy).
  • `ratchet_header` on the wire is opaque to FORJD — the server must never
    parse or store derived message keys.
  • `crypto_sessions` holds only X25519 *public* keys for discovery; private
    identity / ephemeral keys never leave the client.

Per-tenant / per-session keys
  • Tenant membership (Supabase Auth JWT + RLS) gates who may ingest/read.
  • Session identity is client-generated (`session_id` / `key_id`).
  • Message keys are derived per session (and per ratchet step) on the client.
  • The ingest API validates envelope *shape* and membership only — it does
    not decrypt. `seal` / `open_envelope` / `derive_session_key` exist for
    client SDKs and tests, never for production E2EE server decryption.

Never put long-term tenant secrets in Settings or the database in plaintext.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

GCM_NONCE_BYTES = 12
AES_KEY_BYTES = 32
X25519_KEY_BYTES = 32
ALGO_AES_256_GCM = "aes-256-gcm"
# HKDF info binds derived keys to FORJD session use (domain separation).
HKDF_INFO_SESSION = b"forjd-session-v1"
HKDF_SALT_SESSION = b"forjd-e2ee-v1"


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


# ---------------------------------------------------------------------------
# X25519 key agreement → AES-256 session key (client / test path only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class X25519KeyPair:
    """Raw X25519 key material. Private key must never be sent to FORJD."""

    private_key: bytes  # 32 bytes
    public_key: bytes  # 32 bytes

    @property
    def public_key_b64(self) -> str:
        return b64encode(self.public_key)

    @property
    def private_key_b64(self) -> str:
        return b64encode(self.private_key)


def generate_x25519_keypair() -> X25519KeyPair:
    """Generate an X25519 identity or ephemeral key pair (client-side)."""
    priv = X25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return X25519KeyPair(private_key=priv.private_bytes_raw(), public_key=pub)


def derive_session_key(
    *,
    private_key: bytes,
    peer_public_key: bytes,
    session_id: str,
) -> bytes:
    """ECDH (X25519) + HKDF-SHA256 → 32-byte AES key.

    Client-only. FORJD never calls this on the E2EE ingest path.
    `session_id` is mixed into HKDF info so keys are per-session.
    """
    if len(private_key) != X25519_KEY_BYTES or len(peer_public_key) != X25519_KEY_BYTES:
        raise CryptoError("X25519 keys must be 32 bytes")
    if not session_id:
        raise CryptoError("session_id required")
    try:
        priv = X25519PrivateKey.from_private_bytes(private_key)
        peer = X25519PublicKey.from_public_bytes(peer_public_key)
        shared = priv.exchange(peer)
    except Exception as exc:  # noqa: BLE001
        raise CryptoError("X25519 ECDH failed") from exc

    info = HKDF_INFO_SESSION + b"|" + session_id.encode("utf-8")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=AES_KEY_BYTES,
        salt=HKDF_SALT_SESSION,
        info=info,
    ).derive(shared)


def validate_x25519_public_b64(value: str) -> str:
    """Validate a base64-encoded X25519 public key (32 bytes)."""
    raw = b64decode(value)
    if len(raw) != X25519_KEY_BYTES:
        raise CryptoError("X25519 public key must be 32 bytes")
    try:
        X25519PublicKey.from_public_bytes(raw)
    except Exception as exc:  # noqa: BLE001
        raise CryptoError("invalid X25519 public key") from exc
    return value


# ---------------------------------------------------------------------------
# AES-256-GCM sealed envelopes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SealedEnvelope:
    """Wire format for an E2EE telemetry payload (encrypted_payload = ciphertext)."""

    algo: str
    key_id: str
    nonce: str  # base64
    ciphertext: str  # base64 (ciphertext || tag) — the encrypted_payload
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


def seal_with_x25519(
    plaintext: bytes,
    *,
    private_key: bytes,
    peer_public_key: bytes,
    session_id: str,
    tenant_id: str,
    client_event_id: str,
    ratchet_header: str | None = None,
) -> SealedEnvelope:
    """Derive a session AES key via X25519+HKDF, then seal (client/test helper)."""
    key = derive_session_key(
        private_key=private_key,
        peer_public_key=peer_public_key,
        session_id=session_id,
    )
    return seal(
        plaintext,
        key=key,
        key_id=session_id,
        tenant_id=tenant_id,
        client_event_id=client_event_id,
        ratchet_header=ratchet_header,
    )
