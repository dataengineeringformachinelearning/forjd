"""OSINT + dark-web scanners (crt.sh, HIBP, optional Tor/Ahmia)."""

from __future__ import annotations

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

logger = logging.getLogger("forjd.osint")


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
    url = f"https://crt.sh/?q={domain}&output=json"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OSINT crt.sh failed for %s: %s", domain, exc)
        return []

    subdomains: set[str] = set()
    if not isinstance(payload, list):
        return []
    for entry in payload:
        name_value = str(entry.get("name_value") or "")
        for name in name_value.split("\n"):
            name = name.strip().lower()
            if name.endswith(domain.lower()) and "*" not in name:
                subdomains.add(name)
    return sorted(subdomains)


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
    return {"ok": True, "domain": domain, "subdomains": subs, "persisted": stored}


# --- HIBP breach check ---
async def check_hibp_breaches(
    pool: asyncpg.Pool,
    *,
    account_email: str,
    tenant_id: UUID | None = None,
) -> dict[str, Any]:
    headers = {"User-Agent": "FORJD-OSINT"}
    api_key = (settings.HIBP_API_KEY or "").strip()
    if api_key:
        headers["hibp-api-key"] = api_key
    url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{account_email}"
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            response = await client.get(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("HIBP network error: %s", exc)
        return {"ok": False, "breaches": [], "error": str(exc)}

    if response.status_code == 404:
        return {"ok": True, "breaches": []}
    if response.status_code != 200:
        return {"ok": False, "breaches": [], "error": f"http_{response.status_code}"}

    breaches = response.json()
    if tenant_id is not None:
        await threat_svc.ensure_threat_schema(pool)
        await pool.execute(
            """
            INSERT INTO threat_intelligence (
                tenant_id, is_platform, source, location, is_malicious, raw_payload
            )
            VALUES ($1::uuid, FALSE, 'HIBP', $2, TRUE, $3::jsonb)
            """,
            str(tenant_id),
            account_email,
            json.dumps({"breaches": breaches}),
        )
    return {"ok": True, "breaches": breaches, "count": len(breaches)}


# --- Ahmia / Tor (optional; requires SOCKS proxy) ---
async def search_ahmia(keyword: str) -> dict[str, Any]:
    proxy = (settings.TOR_PROXY_URL or "").strip()
    if not proxy:
        return {"ok": False, "error": "TOR_PROXY_URL not configured"}
    onion = (
        f"http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q={keyword}"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0, proxy=proxy) as client:
            response = await client.get(onion)
        return {"ok": response.status_code == 200, "status_code": response.status_code}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ahmia search failed: %s", exc)
        return {"ok": False, "error": str(exc)}
