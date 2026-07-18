"""Google PageSpeed / Lighthouse scans ."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import quote
from uuid import UUID

import asyncpg
import httpx

from app.core.auth import AuthUser
from app.core.config import settings
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.lighthouse")

PAGESPEED_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


# --- Soft schema ---
async def ensure_lighthouse_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS lighthouse_scans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            performance DOUBLE PRECISION NOT NULL DEFAULT 0,
            accessibility DOUBLE PRECISION NOT NULL DEFAULT 0,
            best_practices DOUBLE PRECISION NOT NULL DEFAULT 0,
            seo DOUBLE PRECISION NOT NULL DEFAULT 0,
            raw_payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


# --- PageSpeed call ---
async def scan_url(url: str, *, timeout: float = 45.0) -> dict[str, float] | None:
    categories = ["performance", "accessibility", "best-practices", "seo"]
    req_url = f"{PAGESPEED_API_URL}?url={quote(url, safe='')}&strategy=mobile"
    for cat in categories:
        req_url += f"&category={cat}"
    api_key = (settings.PAGESPEED_API_KEY or "").strip()
    if api_key:
        req_url += f"&key={api_key}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(req_url)
        if response.status_code == 429:
            logger.warning("Lighthouse quota exceeded for %s", url)
            return None
        if response.status_code != 200:
            logger.error("Lighthouse HTTP %s: %s", response.status_code, response.text[:300])
            return None
        data = response.json()
        cats = (data.get("lighthouseResult") or {}).get("categories") or {}
        return {
            "performance": float((cats.get("performance") or {}).get("score") or 0) * 100,
            "accessibility": float((cats.get("accessibility") or {}).get("score") or 0) * 100,
            "best_practices": float((cats.get("best-practices") or {}).get("score") or 0) * 100,
            "seo": float((cats.get("seo") or {}).get("score") or 0) * 100,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Lighthouse scan failed: %s", exc)
        return None


async def scan_and_store(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    url: str,
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin", "member"}),
    )
    await ensure_lighthouse_schema(pool)
    scores = await scan_url(url)
    if scores is None:
        return {"ok": False, "error": "scan_failed"}
    row = await pool.fetchrow(
        """
        INSERT INTO lighthouse_scans (
            tenant_id, url, performance, accessibility, best_practices, seo, raw_payload
        )
        VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::jsonb)
        RETURNING id::text, tenant_id::text, url, scanned_at, performance, accessibility,
                  best_practices, seo
        """,
        str(tenant_id),
        url,
        scores["performance"],
        scores["accessibility"],
        scores["best_practices"],
        scores["seo"],
        json.dumps(scores),
    )
    return {"ok": True, "scan": dict(row)}


async def list_scans(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    limit: int = 50,
) -> list[dict[str, Any]]:
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    await ensure_lighthouse_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, url, scanned_at, performance, accessibility,
               best_practices, seo
        FROM lighthouse_scans
        WHERE tenant_id = $1::uuid
        ORDER BY scanned_at DESC
        LIMIT $2
        """,
        str(tenant_id),
        max(1, min(limit, 200)),
    )
    return [dict(r) for r in rows]
