"""Pydantic models for tenant-scoped service accounts (M2M / subprocessors)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.sanitize import sanitize_label
from app.core.text_fields import Name128


class ServiceAccountCreate(BaseModel):
    tenant_id: UUID
    name: Name128
    # e.g. "partner-app" — audit / policy label; not a trust boundary by itself.
    subprocessor: str = Field(default="", max_length=64)

    @field_validator("subprocessor", mode="before")
    @classmethod
    def _clean_subprocessor(cls, value: object) -> str:
        return sanitize_label(str(value or ""), max_length=64)

    scopes: list[str] | None = None
    # Extends canonical DEFAULT_SCOPES without making scripts duplicate them.
    include_tenant_erase: bool = False
    # Optional Supabase Auth user for M2M JWTs (app_metadata.forjd).
    auth_user_id: UUID | None = None
    # When true (default), mint an opaque fjsvc_… token returned once.
    mint_opaque_token: bool = True
