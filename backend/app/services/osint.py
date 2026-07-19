"""OSINT + dark-web scanners (crt.sh, HIBP, optional Tor/Ahmia)."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

import asyncpg
import httpx

from app.core.auth import AuthUser
from app.core.config import settings
from app.services import tenants as tenant_svc
from app.services import threat_intel as threat_svc
from app.services.fetchers.crtsh import CrtShFetcher
from app.services.fetchers.hibp import HibpFetcher

logger = logging.getLogger("forjd.osint")

_crtsh = CrtShFetcher()
_hibp = HibpFetcher()


# --- PII helpers (store digests, never raw emails) ---
def _email_location_digest(account_email: str) -> str:
    normalized = account_email.strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# --- Soft schema for discovered endpoints ---
async def ensure_osint_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS discovered_endpoints (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'crt.sh',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, url)
        )
        """
    )


# --- Certificate transparency ---
async def scan_domain_subdomains(domain: str, *, timeout: float = 20.0) -> list[str]:
    result = await _crtsh.fetch({"domain": domain, "timeout": timeout})
    if not result.ok or result.data is None:
        return []
    return list(result.data.subdomains)


async def scan_and_persist_domain(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    domain: str,
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin"}),
    )
    await ensure_osint_schema(pool)
    subs = await scan_domain_subdomains(domain)
    stored = 0
    for sub in subs:
        await pool.execute(
            """
            INSERT INTO discovered_endpoints (tenant_id, url, source)
            VALUES ($1::uuid, $2, 'crt.sh')
            ON CONFLICT (tenant_id, url) DO NOTHING
            """,
            str(tenant_id),
            f"https://{sub}",
        )
        stored += 1
    return {
        "ok": True,
        "domain": domain,
        "subdomains": subs,
        "persisted": stored,
        "provider": _crtsh.name,
    }


# --- HIBP breach check ---
async def check_hibp_breaches(
    pool: asyncpg.Pool,
    *,
    account_email: str,
    tenant_id: UUID | None = None,
) -> dict[str, Any]:
    fetch = await _hibp.fetch({"email": account_email})
    if not fetch.ok or fetch.data is None:
        return {
            "ok": False,
            "breaches": [],
            "error": fetch.error or "hibp_failed",
            "provider": _hibp.name,
        }

    if fetch.data.not_found:
        return {"ok": True, "breaches": [], "provider": _hibp.name}

    breaches = list(fetch.data.breaches)
    if tenant_id is not None:
        digest = _email_location_digest(account_email)
        await threat_svc.ensure_threat_schema(pool)
        await pool.execute(
            """
            INSERT INTO threat_intelligence (
                tenant_id, is_platform, source, location, is_malicious, raw_payload
            )
            VALUES ($1::uuid, FALSE, 'HIBP', $2, TRUE, $3::jsonb)
            """,
            str(tenant_id),
            digest,
            json.dumps({"breaches": breaches, "account_digest": digest}),
        )
    return {
        "ok": True,
        "breaches": breaches,
        "count": len(breaches),
        "provider": _hibp.name,
    }


# --- Ahmia / Tor (optional; requires SOCKS proxy) ---
async def search_ahmia(keyword: str) -> dict[str, Any]:
    proxy = (settings.TOR_PROXY_URL or "").strip()
    if not proxy:
        return {
            "ok": False,
            "error": "TOR_PROXY_URL not configured",
            "provider": "ahmia",
        }
    onion = (
        f"http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q={keyword}"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0, proxy=proxy) as client:
            response = await client.get(onion)
        return {
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "provider": "ahmia",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ahmia search failed: %s", exc)
        return {"ok": False, "error": str(exc), "provider": "ahmia"}
