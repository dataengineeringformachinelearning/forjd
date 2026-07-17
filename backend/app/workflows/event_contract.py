"""Validation and integrity helpers for versioned projection events (from DEML)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Final

IDEMPOTENCY_KEY_MIN_LENGTH: Final[int] = 16
IDEMPOTENCY_KEY_MAX_LENGTH: Final[int] = 128
IDEMPOTENCY_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class IdempotencyConflictError(ValueError):
    """Raised when one idempotency key is reused for a different payload."""


# --- Idempotency key validation ---
def validate_idempotency_key(value: object) -> str:
    """Return a safe idempotency key or reject the event contract."""
    if not isinstance(value, str):
        raise ValueError("idempotency_key must be a string")
    if not IDEMPOTENCY_KEY_MIN_LENGTH <= len(value) <= IDEMPOTENCY_KEY_MAX_LENGTH:
        raise ValueError(
            f"idempotency_key must be {IDEMPOTENCY_KEY_MIN_LENGTH}-"
            f"{IDEMPOTENCY_KEY_MAX_LENGTH} characters"
        )
    if IDEMPOTENCY_KEY_PATTERN.fullmatch(value) is None:
        raise ValueError("idempotency_key contains unsupported characters")
    return value


# --- Canonical payload hash (detect key reuse with changed data) ---
def projection_payload_hash(action: str, payload: dict[str, Any]) -> str:
    """Hash the action and canonical payload to detect key reuse with changed data."""
    encoded = json.dumps(
        {"action": action, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
