"""Tenant status pages — operational visibility for any SaaS product."""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.status")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


# --- Create / list (JWT + membership) ---
async def create_page(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    slug: str,
    title: str,
    description: str = "",
    is_published: bool = False,
) -> dict[str, Any]:
    await tenant_svc.ensure_secure_schema(pool)
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin"}),
    )
    slug = slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValueError("invalid slug")
    row = await pool.fetchrow(
        """
        INSERT INTO status_pages (tenant_id, slug, title, description, is_published)
        VALUES ($1::uuid, $2, $3, $4, $5)
        RETURNING id::text, tenant_id::text, slug, title, description,
                  is_published, created_at, updated_at
        """,
        str(tenant_id),
        slug,
        title.strip(),
        description,
        is_published,
    )
    return _page_dict(row)


async def list_pages(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
) -> list[dict[str, Any]]:
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, slug, title, description,
               is_published, created_at, updated_at
        FROM status_pages
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        """,
        str(tenant_id),
    )
    return [_page_dict(r) for r in rows]


# --- Public read by slug ---
async def get_published_page(
    pool: asyncpg.Pool,
    *,
    slug: str,
) -> dict[str, Any] | None:
    page = await pool.fetchrow(
        """
        SELECT id::text, tenant_id::text, slug, title, description,
               is_published, created_at, updated_at
        FROM status_pages
        WHERE slug = $1 AND is_published = TRUE
        """,
        slug.strip().lower(),
    )
    if page is None:
        return None
    services = await pool.fetch(
        """
        SELECT id::text, name, status, description, sort_order, updated_at
        FROM status_services
        WHERE page_id = $1::uuid
        ORDER BY sort_order ASC, name ASC
        """,
        page["id"],
    )
    incidents = await pool.fetch(
        """
        SELECT id::text, title, status, severity, body, started_at, resolved_at
        FROM status_incidents
        WHERE page_id = $1::uuid
        ORDER BY started_at DESC
        LIMIT 20
        """,
        page["id"],
    )
    overall = _overall_status([s["status"] for s in services])
    return {
        **_page_dict(page),
        "overall_status": overall,
        "services": [
            {
                "id": s["id"],
                "name": s["name"],
                "status": s["status"],
                "description": s["description"],
                "sort_order": s["sort_order"],
                "updated_at": s["updated_at"].isoformat(),
            }
            for s in services
        ],
        "incidents": [
            {
                "id": i["id"],
                "title": i["title"],
                "status": i["status"],
                "severity": i["severity"],
                "body": i["body"],
                "started_at": i["started_at"].isoformat(),
                "resolved_at": i["resolved_at"].isoformat() if i["resolved_at"] else None,
            }
            for i in incidents
        ],
    }


# --- Services / incidents ---
async def upsert_service(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    page_id: UUID,
    name: str,
    status: str = "operational",
    description: str = "",
    sort_order: int = 0,
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin", "member"}),
    )
    page = await _require_page(pool, tenant_id=tenant_id, page_id=page_id)
    row = await pool.fetchrow(
        """
        INSERT INTO status_services (page_id, tenant_id, name, status, description, sort_order)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6)
        RETURNING id::text, name, status, description, sort_order, updated_at
        """,
        page["id"],
        str(tenant_id),
        name.strip(),
        status,
        description,
        sort_order,
    )
    return {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "description": row["description"],
        "sort_order": row["sort_order"],
        "updated_at": row["updated_at"].isoformat(),
        "page_id": page["id"],
    }


async def create_incident(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    page_id: UUID,
    title: str,
    status: str = "investigating",
    severity: str = "minor",
    body: str = "",
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin", "member"}),
    )
    page = await _require_page(pool, tenant_id=tenant_id, page_id=page_id)
    row = await pool.fetchrow(
        """
        INSERT INTO status_incidents (
            page_id, tenant_id, title, status, severity, body
        )
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6)
        RETURNING id::text, title, status, severity, body, started_at, resolved_at
        """,
        page["id"],
        str(tenant_id),
        title.strip(),
        status,
        severity,
        body,
    )
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "severity": row["severity"],
        "body": row["body"],
        "started_at": row["started_at"].isoformat(),
        "resolved_at": None,
        "page_id": page["id"],
    }


# --- Helpers ---
async def _require_page(
    pool: asyncpg.Pool, *, tenant_id: UUID, page_id: UUID
) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        SELECT id::text FROM status_pages
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        """,
        str(page_id),
        str(tenant_id),
    )
    if row is None:
        raise ValueError("status page not found")
    return {"id": row["id"]}


def _page_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "slug": row["slug"],
        "title": row["title"],
        "description": row["description"],
        "is_published": row["is_published"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def _overall_status(statuses: list[str]) -> str:
    if not statuses:
        return "operational"
    rank = {
        "major_outage": 4,
        "partial_outage": 3,
        "degraded": 2,
        "maintenance": 1,
        "operational": 0,
    }
    return max(statuses, key=lambda s: rank.get(s, 0))
