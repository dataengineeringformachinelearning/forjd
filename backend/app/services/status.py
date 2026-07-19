"""Tenant status pages — operational visibility for any SaaS product.

Managed routes accept human members or scoped service principals
(`status:read` / `status:write`). Public published slug stays unauthenticated.
"""

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
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin"}),
        required_scopes=frozenset({"status:write"}),
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
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"status:read"}),
    )
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


# --- Page update / delete ---
async def update_page(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    page_id: UUID,
    slug: str | None = None,
    title: str | None = None,
    description: str | None = None,
    is_published: bool | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin"}),
        required_scopes=frozenset({"status:write"}),
    )
    await _require_page(pool, tenant_id=tenant_id, page_id=page_id)
    if slug is not None:
        slug = slug.strip().lower()
        if not _SLUG_RE.match(slug):
            raise ValueError("invalid slug")
    row = await pool.fetchrow(
        """
        UPDATE status_pages SET
            slug = COALESCE($3, slug),
            title = COALESCE($4, title),
            description = COALESCE($5, description),
            is_published = COALESCE($6, is_published),
            updated_at = NOW()
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        RETURNING id::text, tenant_id::text, slug, title, description,
                  is_published, created_at, updated_at
        """,
        str(page_id),
        str(tenant_id),
        slug,
        title.strip() if isinstance(title, str) else None,
        description,
        is_published,
    )
    if row is None:
        raise ValueError("status page not found")
    return _page_dict(row)


async def delete_page(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    page_id: UUID,
) -> None:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin"}),
        required_scopes=frozenset({"status:write"}),
    )
    result = await pool.execute(
        "DELETE FROM status_pages WHERE id = $1::uuid AND tenant_id = $2::uuid",
        str(page_id),
        str(tenant_id),
    )
    if str(result).endswith(" 0"):
        raise ValueError("status page not found")


# --- Services / incidents ---
async def list_services(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    page_id: UUID,
) -> list[dict[str, Any]]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"status:read"}),
    )
    await _require_page(pool, tenant_id=tenant_id, page_id=page_id)
    rows = await pool.fetch(
        """
        SELECT id::text, name, status, description, sort_order, updated_at, page_id::text
        FROM status_services
        WHERE page_id = $1::uuid AND tenant_id = $2::uuid
        ORDER BY sort_order ASC, name ASC
        """,
        str(page_id),
        str(tenant_id),
    )
    return [_service_dict(r) for r in rows]


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
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"status:write"}),
    )
    page = await _require_page(pool, tenant_id=tenant_id, page_id=page_id)
    # Update existing row with same name on the page; else insert.
    existing = await pool.fetchrow(
        """
        SELECT id::text FROM status_services
        WHERE page_id = $1::uuid AND tenant_id = $2::uuid AND lower(name) = lower($3)
        LIMIT 1
        """,
        page["id"],
        str(tenant_id),
        name.strip(),
    )
    if existing is not None:
        row = await pool.fetchrow(
            """
            UPDATE status_services SET
                name = $3, status = $4, description = $5, sort_order = $6, updated_at = NOW()
            WHERE id = $1::uuid AND tenant_id = $2::uuid
            RETURNING id::text, name, status, description, sort_order, updated_at, page_id::text
            """,
            existing["id"],
            str(tenant_id),
            name.strip(),
            status,
            description,
            sort_order,
        )
    else:
        row = await pool.fetchrow(
            """
            INSERT INTO status_services (page_id, tenant_id, name, status, description, sort_order)
            VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6)
            RETURNING id::text, name, status, description, sort_order, updated_at, page_id::text
            """,
            page["id"],
            str(tenant_id),
            name.strip(),
            status,
            description,
            sort_order,
        )
    return _service_dict(row)


async def update_service(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    service_id: UUID,
    name: str | None = None,
    status: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"status:write"}),
    )
    row = await pool.fetchrow(
        """
        UPDATE status_services SET
            name = COALESCE($3, name),
            status = COALESCE($4, status),
            description = COALESCE($5, description),
            sort_order = COALESCE($6, sort_order),
            updated_at = NOW()
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        RETURNING id::text, name, status, description, sort_order, updated_at, page_id::text
        """,
        str(service_id),
        str(tenant_id),
        name.strip() if isinstance(name, str) else None,
        status,
        description,
        sort_order,
    )
    if row is None:
        raise ValueError("status service not found")
    return _service_dict(row)


async def delete_service(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    service_id: UUID,
) -> None:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"status:write"}),
    )
    result = await pool.execute(
        "DELETE FROM status_services WHERE id = $1::uuid AND tenant_id = $2::uuid",
        str(service_id),
        str(tenant_id),
    )
    if str(result).endswith(" 0"):
        raise ValueError("status service not found")


async def list_incidents(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    page_id: UUID,
) -> list[dict[str, Any]]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"status:read"}),
    )
    await _require_page(pool, tenant_id=tenant_id, page_id=page_id)
    rows = await pool.fetch(
        """
        SELECT id::text, title, status, severity, body, started_at, resolved_at, page_id::text
        FROM status_incidents
        WHERE page_id = $1::uuid AND tenant_id = $2::uuid
        ORDER BY started_at DESC
        LIMIT 100
        """,
        str(page_id),
        str(tenant_id),
    )
    return [_incident_dict(r) for r in rows]


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
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"status:write"}),
    )
    page = await _require_page(pool, tenant_id=tenant_id, page_id=page_id)
    row = await pool.fetchrow(
        """
        INSERT INTO status_incidents (
            page_id, tenant_id, title, status, severity, body,
            resolved_at
        )
        VALUES (
            $1::uuid, $2::uuid, $3, $4, $5, $6,
            CASE WHEN $4 = 'resolved' THEN NOW() ELSE NULL END
        )
        RETURNING id::text, title, status, severity, body, started_at, resolved_at, page_id::text
        """,
        page["id"],
        str(tenant_id),
        title.strip(),
        status,
        severity,
        body,
    )
    return _incident_dict(row)


async def update_incident(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    incident_id: UUID,
    title: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"status:write"}),
    )
    row = await pool.fetchrow(
        """
        UPDATE status_incidents SET
            title = COALESCE($3, title),
            status = COALESCE($4, status),
            severity = COALESCE($5, severity),
            body = COALESCE($6, body),
            resolved_at = CASE
                WHEN $4 = 'resolved' THEN COALESCE(resolved_at, NOW())
                WHEN $4 IS NOT NULL AND $4 <> 'resolved' THEN NULL
                ELSE resolved_at
            END
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        RETURNING id::text, title, status, severity, body, started_at, resolved_at, page_id::text
        """,
        str(incident_id),
        str(tenant_id),
        title.strip() if isinstance(title, str) else None,
        status,
        severity,
        body,
    )
    if row is None:
        raise ValueError("status incident not found")
    return _incident_dict(row)


async def delete_incident(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    incident_id: UUID,
) -> None:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"status:write"}),
    )
    result = await pool.execute(
        "DELETE FROM status_incidents WHERE id = $1::uuid AND tenant_id = $2::uuid",
        str(incident_id),
        str(tenant_id),
    )
    if str(result).endswith(" 0"):
        raise ValueError("status incident not found")


# --- Helpers ---
async def _require_page(pool: asyncpg.Pool, *, tenant_id: UUID, page_id: UUID) -> dict[str, Any]:
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


def _service_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "description": row["description"],
        "sort_order": row["sort_order"],
        "updated_at": row["updated_at"].isoformat(),
        "page_id": row["page_id"],
    }


def _incident_dict(row: Any) -> dict[str, Any]:
    resolved = row["resolved_at"]
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "severity": row["severity"],
        "body": row["body"],
        "started_at": row["started_at"].isoformat(),
        "resolved_at": resolved.isoformat() if resolved else None,
        "page_id": row["page_id"],
    }


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
