"""Strict, selectively disclosed security-signal contract.

This lane is intentionally separate from sealed evidence.  It accepts only the
small amount of normalized metadata FORJD needs for SIEM correlation; raw
payloads, ciphertext, credentials, and direct user identifiers are rejected.
"""

from __future__ import annotations

import ipaddress
import math
import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Severity = Literal["informational", "low", "medium", "high", "critical"]
SignalCategory = Literal[
    "authentication",
    "malware",
    "network",
    "data_loss",
    "vulnerability",
    "cloud",
    "endpoint",
    "application",
    "threat_intelligence",
    "other",
]
ObservableType = Literal[
    "ipv4",
    "ipv6",
    "domain",
    "hostname",
    "url_path",
    "file_sha256",
    "process_sha256",
    "cve",
    "cloud_resource",
    "device_pseudonym",
    "other_hash",
]

_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TYPE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_FORBIDDEN_KEY_PARTS = (
    "raw",
    "ciphertext",
    "plaintext",
    "password",
    "secret",
    "token",
    "authorization",
    "cookie",
    "email",
    "username",
    "full_name",
)


def _reject_sensitive_text(value: str, *, field_name: str) -> str:
    clean = value.strip()
    if _EMAIL_RE.search(clean):
        raise ValueError(f"{field_name} must use a pseudonym, not an email address")
    lowered = clean.lower()
    if "-----begin " in lowered or "bearer " in lowered or _JWT_RE.search(clean):
        raise ValueError(f"{field_name} contains credential-like material")
    return clean


def validate_signal_metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Validate a small, shallow, PII-minimized metadata map."""
    if len(value) > 32:
        raise ValueError("metadata may contain at most 32 keys")
    return _normalize_metadata_object(value, path="metadata", depth=0)


def _normalize_metadata_object(
    value: dict[str, Any],
    *,
    path: str,
    depth: int,
) -> dict[str, Any]:
    if depth > 2:
        raise ValueError("metadata nesting may not exceed two levels")
    if len(value) > (32 if depth == 0 else 16):
        raise ValueError(f"{path} contains too many keys")
    clean: dict[str, Any] = {}
    for raw_key, item in value.items():
        key = str(raw_key).strip()
        lowered = key.lower()
        if not key or len(key) > 64:
            raise ValueError("metadata keys must be 1-64 characters")
        if any(part in lowered for part in _FORBIDDEN_KEY_PARTS):
            raise ValueError(f"metadata key {key!r} is not allowed")
        item_path = f"{path}.{key}"
        if isinstance(item, str):
            if len(item) > 512:
                raise ValueError(f"metadata value {key!r} is too long")
            clean[key] = _reject_sensitive_text(item, field_name=item_path)
        elif isinstance(item, bool) or item is None:
            clean[key] = item
        elif isinstance(item, (int, float)):
            numeric = float(item)
            if not math.isfinite(numeric) or not -1_000_000_000 <= numeric <= 1_000_000_000:
                raise ValueError(f"metadata value {key!r} is outside the allowed range")
            clean[key] = item
        elif isinstance(item, dict):
            clean[key] = _normalize_metadata_object(item, path=item_path, depth=depth + 1)
        elif isinstance(item, list):
            if len(item) > 20:
                raise ValueError(f"metadata list {key!r} is too long")
            normalized: list[str | int | float | bool | None] = []
            for child in item:
                if isinstance(child, str):
                    if len(child) > 256:
                        raise ValueError(f"metadata list item {key!r} is too long")
                    normalized.append(_reject_sensitive_text(child, field_name=f"metadata.{key}"))
                elif isinstance(child, bool) or child is None or isinstance(child, (int, float)):
                    if isinstance(child, (int, float)) and not isinstance(child, bool):
                        numeric = float(child)
                        if not math.isfinite(numeric):
                            raise ValueError(f"metadata list item {key!r} must be finite")
                    normalized.append(child)
                else:
                    raise ValueError("metadata lists may contain only scalar values")
            clean[key] = normalized
        else:
            raise ValueError("metadata values must be scalar or bounded scalar lists")
    return clean


class SecurityObservable(BaseModel):
    """A normalized observable that avoids direct user identifiers."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: ObservableType
    value: str = Field(..., min_length=1, max_length=512)
    role: Literal["source", "destination", "target", "related"] = "related"
    confidence: int = Field(default=50, ge=0, le=100)

    @model_validator(mode="after")
    def _validate_value(self) -> SecurityObservable:
        value = _reject_sensitive_text(self.value, field_name="observable.value")
        if self.type in {"ipv4", "ipv6"}:
            parsed = ipaddress.ip_address(value)
            expected = 4 if self.type == "ipv4" else 6
            if parsed.version != expected:
                raise ValueError(f"{self.type} observable has the wrong address family")
            value = str(parsed)
        elif self.type in {"file_sha256", "process_sha256", "other_hash"}:
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{self.type} must be a SHA-256 hex digest")
            value = value.lower()
        elif self.type == "cve":
            if not _CVE_RE.fullmatch(value):
                raise ValueError("cve observable must use CVE-YYYY-NNNN format")
            value = value.upper()
        elif self.type == "url_path":
            if not value.startswith("/") or "?" in value or "#" in value:
                raise ValueError("url_path must be a path without query or fragment")
        elif "@" in value:
            raise ValueError("observable values may not contain direct user identifiers")
        self.value = value
        return self


class CreateSecuritySignalRequest(BaseModel):
    """Normalized signal input; raw evidence belongs on the sealed ingest path."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tenant_id: UUID
    client_signal_id: str = Field(..., min_length=1, max_length=128)
    observed_at: datetime
    source: str = Field(..., min_length=1, max_length=128)
    category: SignalCategory
    signal_type: str = Field(..., min_length=1, max_length=128)
    severity: Severity = "medium"
    title: str = Field(..., min_length=1, max_length=255)
    summary: str = Field(default="", max_length=2048)
    confidence: int = Field(default=50, ge=0, le=100)
    observables: list[SecurityObservable] = Field(default_factory=list, max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlate: bool = True
    run_playbooks: bool = True

    @field_validator("client_signal_id")
    @classmethod
    def _client_signal_id(cls, value: str) -> str:
        if not _CLIENT_ID_RE.fullmatch(value):
            raise ValueError("client_signal_id contains unsupported characters")
        return value

    @field_validator("source", "signal_type")
    @classmethod
    def _machine_names(cls, value: str, info: Any) -> str:
        normalized = value.strip().lower()
        if not _TYPE_RE.fullmatch(normalized):
            raise ValueError(f"{info.field_name} must be a lowercase machine identifier")
        return normalized

    @field_validator("title", "summary")
    @classmethod
    def _safe_text(cls, value: str, info: Any) -> str:
        return _reject_sensitive_text(value, field_name=info.field_name)

    @field_validator("observed_at")
    @classmethod
    def _timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value.astimezone(UTC)

    @field_validator("metadata")
    @classmethod
    def _metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_signal_metadata(value)
