"""Threat intelligence ingestion and lookup (DEML abuse.ch / TAXII path)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

import asyncpg
import httpx

from app.core.auth import AuthUser
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.threat_intel")

ABUSE_CH_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist.txt"
_IPV4_RE = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)$")


# --- Soft schema for local/dev ---
async def ensure_threat_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS threat_intelligence (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID REFERENCES tenants (id) ON DELETE CASCADE,
            is_platform BOOLEAN NOT NULL DEFAULT FALSE,
            source TEXT NOT NULL,
            ip_address INET,
            location TEXT,
            abuse_confidence_score INT NOT NULL DEFAULT 0,
            otx_pulses INT NOT NULL DEFAULT 0,
            is_malicious BOOLEAN NOT NULL DEFAULT FALSE,
            raw_payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


# --- Abuse.ch IP blocklist fetch ---
async def fetch_abuse_ch_ips(*, timeout: float = 15.0) -> list[str]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(ABUSE_CH_URL)
        response.raise_for_status()
    bad_ips: list[str] = []
    for line in response.text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if _IPV4_RE.match(line):
            bad_ips.append(line)
    return bad_ips


async def replace_platform_feed(
    pool: asyncpg.Pool,
    *,
    source: str,
    ips: list[str],
    abuse_confidence_score: int = 100,
) -> int:
    """Replace platform-scoped indicators for a source (no tenant_id)."""
    await ensure_threat_schema(pool)
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """
            DELETE FROM threat_intelligence
            WHERE is_platform = TRUE AND tenant_id IS NULL AND source = $1
            """,
            source,
        )
        if not ips:
            return 0
        await conn.executemany(
            """
            INSERT INTO threat_intelligence (
                tenant_id, is_platform, source, ip_address,
                abuse_confidence_score, is_malicious
            )
            VALUES (NULL, TRUE, $1, $2::inet, $3, TRUE)
            ON CONFLICT DO NOTHING
            """,
            [(source, ip, abuse_confidence_score) for ip in ips],
        )
    return len(ips)


async def refresh_abuse_ch_platform(pool: asyncpg.Pool) -> dict[str, Any]:
    ips = await fetch_abuse_ch_ips()
    count = await replace_platform_feed(pool, source="abuse.ch", ips=ips)
    logger.info("refreshed platform threat intel from abuse.ch: %d ips", count)
    return {"ok": True, "source": "abuse.ch", "count": count}


# --- TAXII / STIX indicator parse ---
def parse_stix_ipv4_indicators(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract ipv4 indicators from STIX 2.x objects (basic pattern parse)."""
    out: list[dict[str, Any]] = []
    for obj in objects:
        if obj.get("type") != "indicator":
            continue
        pattern = str(obj.get("pattern") or "")
        if "ipv4-addr:value" not in pattern:
            continue
        parts = pattern.split("'")
        if len(parts) < 3:
            continue
        ip = parts[1].strip()
        if not _IPV4_RE.match(ip):
            continue
        out.append({"ip_address": ip, "raw_payload": obj})
    return out


async def ingest_taxii_indicators(
    pool: asyncpg.Pool,
    *,
    source: str,
    indicators: list[dict[str, Any]],
    tenant_id: UUID | None = None,
    is_platform: bool = True,
) -> int:
    await ensure_threat_schema(pool)
    if not indicators:
        return 0
    rows: list[tuple[Any, ...]] = []
    for ind in indicators:
        ip = ind.get("ip_address")
        if not ip:
            continue
        payload = json.dumps(ind.get("raw_payload") or {})
        if is_platform:
            rows.append((None, True, source, str(ip), 100, True, payload))
        else:
            if tenant_id is None:
                raise ValueError("tenant_id required for non-platform TAXII ingest")
            rows.append((str(tenant_id), False, source, str(ip), 100, True, payload))
    if not rows:
        return 0
    await pool.executemany(
        """
        INSERT INTO threat_intelligence (
            tenant_id, is_platform, source, ip_address,
            abuse_confidence_score, is_malicious, raw_payload
        )
        VALUES ($1::uuid, $2, $3, $4::inet, $5, $6, $7::jsonb)
        ON CONFLICT DO NOTHING
        """,
        rows,
    )
    return len(rows)


async def fetch_taxii_collection(
    collection_url: str,
    *,
    username: str | None = None,
    password: str | None = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    headers = {"Accept": "application/taxii+json;version=2.1"}
    auth = (username, password) if username and password else None
    async with httpx.AsyncClient(timeout=timeout, headers=headers, auth=auth) as client:
        response = await client.get(collection_url)
        response.raise_for_status()
        bundle = response.json()
    objects = bundle.get("objects") if isinstance(bundle, dict) else None
    if not isinstance(objects, list):
        return []
    return parse_stix_ipv4_indicators(objects)


# --- Lookup / list (JWT + membership for tenant scope) ---
async def lookup_ip(
    pool: asyncpg.Pool,
    *,
    ip_address: str,
    tenant_id: UUID | None = None,
) -> list[dict[str, Any]]:
    await ensure_threat_schema(pool)
    if tenant_id is not None:
        rows = await pool.fetch(
            """
            SELECT id::text, tenant_id::text, is_platform, source, host(ip_address) AS ip_address,
                   abuse_confidence_score, is_malicious, created_at
            FROM threat_intelligence
            WHERE ip_address = $1::inet
              AND (is_platform = TRUE OR tenant_id = $2::uuid)
            ORDER BY is_platform DESC, created_at DESC
            LIMIT 50
            """,
            ip_address,
            str(tenant_id),
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id::text, tenant_id::text, is_platform, source, host(ip_address) AS ip_address,
                   abuse_confidence_score, is_malicious, created_at
            FROM threat_intelligence
            WHERE ip_address = $1::inet AND is_platform = TRUE
            ORDER BY created_at DESC
            LIMIT 50
            """,
            ip_address,
        )
    return [_row(r) for r in rows]


async def list_recent(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    limit: int = 100,
) -> list[dict[str, Any]]:
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    await ensure_threat_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, is_platform, source, host(ip_address) AS ip_address,
               abuse_confidence_score, is_malicious, created_at
        FROM threat_intelligence
        WHERE is_platform = TRUE OR tenant_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        str(tenant_id),
        max(1, min(limit, 500)),
    )
    return [_row(r) for r in rows]


def _row(r: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": r["id"],
        "tenant_id": r["tenant_id"],
        "is_platform": bool(r["is_platform"]),
        "source": r["source"],
        "ip_address": r["ip_address"],
        "abuse_confidence_score": int(r["abuse_confidence_score"]),
        "is_malicious": bool(r["is_malicious"]),
        "created_at": r["created_at"],
    }
