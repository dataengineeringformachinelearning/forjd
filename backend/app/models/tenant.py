"""Tenant / membership API models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.text_fields import Name128, Slug64


# --- Create ---
class TenantCreate(BaseModel):
    slug: Slug64
    name: Name128
    key_directory_id: str | None = Field(default=None, max_length=256)


# --- Responses ---
class TenantOut(BaseModel):
    id: UUID
    slug: str
    name: str
    key_directory_id: str | None
    created_at: datetime
    role: str | None = None


class TenantMemberOut(BaseModel):
    tenant_id: UUID
    user_id: UUID
    role: str
    created_at: datetime
