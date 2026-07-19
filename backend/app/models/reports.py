"""Strict contract for tenant-scoped report documents.

Report documents carry bounded, pre-redacted text (e.g. partner issue
reports) plus a PII-minimized context map. Raw payloads, ciphertext, and
credentials are rejected — sealed evidence belongs on the ingest lane.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.siem import _reject_sensitive_text, validate_signal_metadata

_KIND_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_PSEUDONYM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class CreateReportDocumentRequest(BaseModel):
    """Partner-submitted report document; text is screened, never raw evidence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tenant_id: UUID
    # Stable partner-generated identity. FORJD combines this with a server-side
    # content fingerprint so ambiguous retries are safe but key reuse is not.
    client_report_id: UUID
    kind: str = Field(default="issue_report", min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(default="", max_length=8000)
    context: dict[str, Any] = Field(default_factory=dict)
    # Stable opaque handle chosen by the partner (never an email / user id).
    submitted_by_pseudonym: str | None = Field(default=None, max_length=128)

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _KIND_RE.fullmatch(normalized):
            raise ValueError("kind must be a lowercase machine identifier")
        return normalized

    @field_validator("title", "body")
    @classmethod
    def _safe_text(cls, value: str, info: Any) -> str:
        return _reject_sensitive_text(value, field_name=info.field_name)

    @field_validator("submitted_by_pseudonym")
    @classmethod
    def _pseudonym(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _PSEUDONYM_RE.fullmatch(value) or "@" in value:
            raise ValueError("submitted_by_pseudonym must be an opaque handle")
        return value

    @field_validator("context")
    @classmethod
    def _context(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_signal_metadata(value)
