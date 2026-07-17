"""Tenant / membership API models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    name: str = Field(..., min_length=1, max_length=128)
    key_directory_id: str | None = Field(default=None, max_length=256)


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
