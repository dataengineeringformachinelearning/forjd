"""Pydantic models for tenant-scoped service accounts (M2M / subprocessors)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ServiceAccountCreate(BaseModel):
    tenant_id: UUID
    name: str = Field(min_length=1, max_length=128)
    # e.g. "partner-app" — audit / policy label; not a trust boundary by itself.
    subprocessor: str = Field(default="", max_length=64)
    scopes: list[str] | None = None
    # Optional Supabase Auth user for M2M JWTs (app_metadata.forjd).
    auth_user_id: UUID | None = None
    # When true (default), mint an opaque fjsvc_… token returned once.
    mint_opaque_token: bool = True
