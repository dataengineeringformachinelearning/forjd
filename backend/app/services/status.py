"""Tenant status pages — operational visibility for any SaaS product.

Managed routes accept human members or scoped service principals
(`status:read` / `status:write`). Public published slug stays unauthenticated.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.status")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_HISTORY_DAYS = 30
_ANALYTICS_WINDOW_HOURS = 24


# --- Public slug aliases (legacy embeds / domain-style URLs) ---
def slugify_identifier(value: str) -> str:
    """Normalize free-form identifiers to FORJD slug charset."""
    return re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")


def public_slug_candidates(raw: str) -> list[str]:
    """Exact, slugified, and domain-stem candidates for published-page lookup.

    Examples: ``joealongi.dev`` → ``joealongi-dev``, ``joealongi``;
    ``joealongi-dev`` stays itself. Only values matching ``_SLUG_RE`` are returned.
    """
    text = (raw or "").strip().lower()
    out: list[str] = []

    def _add(candidate: str) -> None:
        if candidate and candidate not in out and _SLUG_RE.match(candidate):
            out.append(candidate)

    _add(text)
    slugified = slugify_identifier(text)
    _add(slugified)
    if "." in text:
        _add(slugify_identifier(text.split(".", 1)[0]))
    return out


def public_slug_prefix(raw: str) -> str | None:
    """Stem used for unique published-page prefix self-heal (min length 3)."""
    text = (raw or "").strip().lower()
    if not text:
        return None
    stem = text.split(".", 1)[0] if "." in text else text
    prefix = slugify_identifier(stem)
    if len(prefix) < 3 or not _SLUG_RE.match(prefix):
        return None
    return prefix


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
    page = None
    for candidate in public_slug_candidates(slug):
        page = await pool.fetchrow(
            """
            SELECT id::text, tenant_id::text, slug, title, description,
                   is_published, created_at, updated_at
            FROM status_pages
            WHERE slug = $1 AND is_published = TRUE
            """,
            candidate,
        )
        if page is not None:
            break
    # Legacy embeds often used a domain stem (``joealongi``) before the
    # slug was stored as ``joealongi-dev``. Only bind when the match is unique
    # among published pages — same surface as the public directory.
    if page is None:
        prefix = public_slug_prefix(slug)
        if prefix is not None:
            rows = await pool.fetch(
                """
                SELECT id::text, tenant_id::text, slug, title, description,
                       is_published, created_at, updated_at
                FROM status_pages
                WHERE is_published = TRUE
                  AND (slug = $1 OR slug LIKE $1 || '-%')
                LIMIT 2
                """,
                prefix,
            )
            if len(rows) == 1:
                page = rows[0]
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
    service_ids = [str(s["id"]) for s in services]
    telemetry = await _public_page_telemetry(
        pool,
        tenant_id=str(page["tenant_id"]),
        service_ids=service_ids,
    )
    overall = _overall_status([s["status"] for s in services])
    return {
        **_public_page_dict(page),
        "overall_status": overall,
        "overall_uptime": telemetry["overall_uptime"],
        "cumulative_sla": telemetry["overall_uptime"],
        "uptime_history": telemetry["page_history"],
        "p99_latency": telemetry["p99_latency"],
        "total_requests": telemetry["total_requests"],
        "services": [
            {
                "id": s["id"],
                "name": s["name"],
                "status": s["status"],
                "description": s["description"],
                "sort_order": s["sort_order"],
                "updated_at": s["updated_at"].isoformat(),
                "page_id": page["id"],
                "sla": telemetry["service_sla"].get(str(s["id"])),
                "uptime_history": telemetry["service_history"].get(
                    str(s["id"]), telemetry["empty_history"]
                ),
                "p99_latency": telemetry["service_latency"].get(str(s["id"])),
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
        SELECT id::text, name, status, description, probe_url, sort_order,
               updated_at, page_id::text
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
    probe_url: str | None = None,
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
    resolved_probe = _resolve_probe_url(probe_url, description)
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
                name = $3, status = $4, description = $5, probe_url = $6,
                sort_order = $7, updated_at = NOW()
            WHERE id = $1::uuid AND tenant_id = $2::uuid
            RETURNING id::text, name, status, description, probe_url, sort_order,
                      updated_at, page_id::text
            """,
            existing["id"],
            str(tenant_id),
            name.strip(),
            status,
            description,
            resolved_probe,
            sort_order,
        )
    else:
        row = await pool.fetchrow(
            """
            INSERT INTO status_services (
                page_id, tenant_id, name, status, description, probe_url, sort_order
            )
            VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7)
            RETURNING id::text, name, status, description, probe_url, sort_order,
                      updated_at, page_id::text
            """,
            page["id"],
            str(tenant_id),
            name.strip(),
            status,
            description,
            resolved_probe,
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
    probe_url: str | None = None,
    sort_order: int | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"status:write"}),
    )
    explicit_probe: str | None = None
    clear_probe = False
    if probe_url is not None:
        trimmed = probe_url.strip()
        if trimmed == "":
            clear_probe = True
        else:
            explicit_probe = _resolve_probe_url(trimmed, "")
    row = await pool.fetchrow(
        """
        UPDATE status_services SET
            name = COALESCE($3, name),
            status = COALESCE($4, status),
            description = COALESCE($5, description),
            probe_url = CASE
                WHEN $8::boolean THEN NULL
                WHEN $6::text IS NOT NULL THEN $6
                WHEN COALESCE(probe_url, '') = ''
                     AND $5::text IS NOT NULL
                     AND $5::text ~* '^https?://'
                  THEN BTRIM($5::text)
                ELSE probe_url
            END,
            sort_order = COALESCE($7, sort_order),
            updated_at = NOW()
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        RETURNING id::text, name, status, description, probe_url, sort_order,
                  updated_at, page_id::text
        """,
        str(service_id),
        str(tenant_id),
        name.strip() if isinstance(name, str) else None,
        status,
        description,
        explicit_probe,
        sort_order,
        clear_probe,
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


def _resolve_probe_url(probe_url: str | None, description: str) -> str | None:
    """Prefer explicit probe_url; else use http(s) description as the probe target."""
    for candidate in (probe_url, description):
        if not isinstance(candidate, str):
            continue
        trimmed = candidate.strip()
        if trimmed.lower().startswith(("http://", "https://")):
            return trimmed
    if isinstance(probe_url, str) and probe_url.strip() == "":
        return None
    return None


def _service_dict(row: Any) -> dict[str, Any]:
    probe = row["probe_url"] if "probe_url" in row else None
    return {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "description": row["description"],
        "probe_url": probe,
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


def _public_page_dict(row: Any) -> dict[str, Any]:
    """Public slug DTO — omit tenant_id to avoid tenant enumeration."""
    page = _page_dict(row)
    page.pop("tenant_id", None)
    return page


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


# --- Public telemetry (probe history + analytics KPIs) ---
def _day_status(active: int, total: int) -> tuple[str, float | None]:
    if total <= 0:
        return "no_data", None
    uptime = round(100.0 * active / total, 2)
    if active == total:
        return "up", uptime
    if active == 0:
        return "down", uptime
    return "partial", uptime


def _fill_uptime_history(
    day_stats: dict[date, tuple[int, int]],
    *,
    days: int = _HISTORY_DAYS,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Build oldest→newest daily points; missing days are explicit no_data."""
    end = today or datetime.now(UTC).date()
    history: list[dict[str, Any]] = []
    for offset in range(days - 1, -1, -1):
        day = end - timedelta(days=offset)
        active, total = day_stats.get(day, (0, 0))
        status, uptime = _day_status(active, total)
        history.append({"date": day.isoformat(), "status": status, "uptime": uptime})
    return history


def _uptime_from_history(history: list[dict[str, Any]]) -> float | None:
    samples = [
        float(point["uptime"])
        for point in history
        if point.get("status") != "no_data" and point.get("uptime") is not None
    ]
    if not samples:
        return None
    return round(sum(samples) / len(samples), 2)


def _merge_day_stats(
    rows: list[Any],
    *,
    service_id: str | None = None,
) -> dict[date, tuple[int, int]]:
    """Aggregate probe day rows into day → (active, total)."""
    merged: dict[date, tuple[int, int]] = {}
    for row in rows:
        if service_id is not None and str(row["service_id"]) != service_id:
            continue
        day = row["day"]
        if isinstance(day, datetime):
            day = day.date()
        active = int(row["active"] or 0)
        total = int(row["total"] or 0)
        prev_active, prev_total = merged.get(day, (0, 0))
        merged[day] = (prev_active + active, prev_total + total)
    return merged


async def _probe_day_rollups(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    service_ids: list[str],
    days: int = _HISTORY_DAYS,
) -> list[asyncpg.Record]:
    if not service_ids:
        return []
    since = datetime.now(UTC) - timedelta(days=days)
    return await pool.fetch(
        """
        SELECT service_id::text AS service_id,
               (observed_at AT TIME ZONE 'UTC')::date AS day,
               COUNT(*)::int AS total,
               COUNT(*) FILTER (WHERE is_active)::int AS active,
               COALESCE(
                 percentile_cont(0.99) WITHIN GROUP (ORDER BY response_time_ms),
                 0
               )::float8 AS p99_ms
        FROM health_probe_observations
        WHERE tenant_id = $1::uuid
          AND service_id = ANY($2::uuid[])
          AND observed_at >= $3
        GROUP BY 1, 2
        ORDER BY 2 ASC
        """,
        tenant_id,
        service_ids,
        since,
    )


async def _analytics_kpis_24h(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(hours=_ANALYTICS_WINDOW_HOURS)
    try:
        rollups = await pool.fetch(
            """
            SELECT total_requests, p99_latency_ms
            FROM aggregated_analytics
            WHERE tenant_id = $1::uuid AND bucket_start >= $2
            """,
            tenant_id,
            since,
        )
    except asyncpg.UndefinedTableError:
        return {"total_requests": 0, "p99_latency": None}
    except Exception:
        logger.exception("status: analytics KPI lookup failed for public page")
        return {"total_requests": 0, "p99_latency": None}
    total_req = sum(int(r["total_requests"] or 0) for r in rollups)
    p99 = max((float(r["p99_latency_ms"] or 0) for r in rollups), default=0.0)
    return {
        "total_requests": total_req,
        "p99_latency": round(p99, 2) if rollups else None,
    }


async def _analytics_day_stats(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    days: int = _HISTORY_DAYS,
) -> dict[date, tuple[int, int]]:
    """Map analytics error-rate rollups into probe-shaped (active, total) day stats."""
    since = datetime.now(UTC) - timedelta(days=days)
    try:
        rows = await pool.fetch(
            """
            SELECT (bucket_start AT TIME ZONE 'UTC')::date AS day,
                   COALESCE(SUM(total_requests), 0)::int AS total_requests,
                   COALESCE(AVG(error_rate_percent), 0)::float8 AS error_rate_percent
            FROM aggregated_analytics
            WHERE tenant_id = $1::uuid AND bucket_start >= $2
            GROUP BY 1
            ORDER BY 1 ASC
            """,
            tenant_id,
            since,
        )
    except asyncpg.UndefinedTableError:
        return {}
    except Exception:
        logger.exception("status: analytics day rollup failed for public page")
        return {}
    merged: dict[date, tuple[int, int]] = {}
    for row in rows:
        day = row["day"]
        if isinstance(day, datetime):
            day = day.date()
        total = max(int(row["total_requests"] or 0), 1)
        err = min(max(float(row["error_rate_percent"] or 0), 0.0), 100.0)
        active = int(round(total * (100.0 - err) / 100.0))
        merged[day] = (active, total)
    return merged


async def _public_page_telemetry(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    service_ids: list[str],
) -> dict[str, Any]:
    empty_history = _fill_uptime_history({})
    probe_rows = await _probe_day_rollups(
        pool, tenant_id=tenant_id, service_ids=service_ids
    )
    probe_page_stats = _merge_day_stats(probe_rows)
    page_history = _fill_uptime_history(probe_page_stats)
    # If probes have not accumulated yet, fall back to tenant analytics days.
    if _uptime_from_history(page_history) is None:
        analytics_days = await _analytics_day_stats(pool, tenant_id=tenant_id)
        if analytics_days:
            page_history = _fill_uptime_history(analytics_days)

    service_history: dict[str, list[dict[str, Any]]] = {}
    service_sla: dict[str, float | None] = {}
    service_latency: dict[str, float | None] = {}
    for sid in service_ids:
        history = _fill_uptime_history(_merge_day_stats(probe_rows, service_id=sid))
        if _uptime_from_history(history) is None:
            # Per-service probe gap: reuse page history so bars stay populated.
            history = page_history
        service_history[sid] = history
        service_sla[sid] = _uptime_from_history(history)
        # Latest observed day p99 for that service (if any).
        latest_p99: float | None = None
        latest_day: date | None = None
        for row in probe_rows:
            if str(row["service_id"]) != sid:
                continue
            day = row["day"]
            if isinstance(day, datetime):
                day = day.date()
            if latest_day is None or day > latest_day:
                latest_day = day
                latest_p99 = float(row["p99_ms"] or 0)
        service_latency[sid] = round(latest_p99, 2) if latest_p99 is not None else None

    analytics = await _analytics_kpis_24h(pool, tenant_id=tenant_id)
    probe_p99s = [
        float(row["p99_ms"] or 0)
        for row in probe_rows
        if row["p99_ms"] is not None
    ]
    p99_latency = analytics["p99_latency"]
    if p99_latency is None and probe_p99s:
        p99_latency = round(max(probe_p99s), 2)

    return {
        "empty_history": empty_history,
        "page_history": page_history,
        "overall_uptime": _uptime_from_history(page_history),
        "service_history": service_history,
        "service_sla": service_sla,
        "service_latency": service_latency,
        "p99_latency": p99_latency,
        "total_requests": int(analytics["total_requests"] or 0),
    }
