"""Threat intelligence ingestion and lookup (abuse.ch / TAXII)."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import socket
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import asyncpg
import httpx
from fastapi import HTTPException, status

from app.core.auth import AuthUser, require_user_principal
from app.core.config import settings
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.threat_intel")

ABUSE_CH_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist.txt"
_IPV4_RE = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)$")
_MAX_TAXII_RESPONSE_BYTES = 2 * 1024 * 1024


def require_platform_admin(user: AuthUser) -> AuthUser:
    """Require a human JWT carrying an admin-controlled platform claim.

    Tenant membership is intentionally insufficient for global feed mutation.
    The accepted claim lives only in ``app_metadata`` (admin-controlled in
    Supabase), never ``user_metadata``.
    """
    require_user_principal(user)
    app_metadata = user.raw_claims.get("app_metadata")
    if not isinstance(app_metadata, dict):
        app_metadata = {}
    forjd = app_metadata.get("forjd")
    if not isinstance(forjd, dict):
        forjd = {}
    platform_role = str(forjd.get("platform_role") or app_metadata.get("platform_role") or "")
    if forjd.get("platform_admin") is True or platform_role in {"admin", "owner"}:
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="human platform administrator required",
    )


def _reject_non_public_address(address: str) -> None:
    parsed = ipaddress.ip_address(address)
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    if not parsed.is_global:
        raise ValueError("outbound URL resolves to a non-public network address")


def host_matches_outbound_allowlist(hostname: str, allowlist: str | None = None) -> bool:
    """Match an exact host or an explicit ``*.suffix`` rule on DNS boundaries."""
    normalized = hostname.rstrip(".").lower()
    configured = settings.OUTBOUND_HOST_ALLOWLIST if allowlist is None else allowlist
    for raw_rule in configured.split(","):
        rule = raw_rule.strip().rstrip(".").lower()
        if not rule or "://" in rule or "/" in rule:
            continue
        if rule.startswith("*."):
            suffix = rule[2:]
            if suffix and normalized != suffix and normalized.endswith(f".{suffix}"):
                return True
        elif "*" not in rule and normalized == rule:
            return True
    return False


async def validate_outbound_url(url: str, *, purpose: str) -> str:
    """Validate TAXII/webhook destinations before any network request."""
    clean = url.strip()
    parsed = urlsplit(clean)
    allowed_schemes = {"https"} if settings.is_production else {"https", "http"}
    if parsed.scheme.lower() not in allowed_schemes:
        scheme_hint = "https" if settings.is_production else "http or https"
        raise ValueError(f"{purpose} URL must use {scheme_hint}")
    if parsed.username or parsed.password:
        raise ValueError(f"{purpose} URL must not contain embedded credentials")
    if parsed.fragment:
        raise ValueError(f"{purpose} URL must not contain a fragment")
    hostname = (parsed.hostname or "").rstrip(".").lower()
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"{purpose} URL hostname is invalid") from exc
    if not hostname or hostname in {"localhost", "localhost.localdomain"}:
        raise ValueError(f"{purpose} URL requires a public hostname")
    if hostname.endswith((".local", ".internal", ".localhost")):
        raise ValueError(f"{purpose} URL requires a public hostname")
    if settings.is_production and not host_matches_outbound_allowlist(hostname):
        raise ValueError(f"{purpose} hostname is not in OUTBOUND_HOST_ALLOWLIST")
    try:
        _reject_non_public_address(hostname)
    except ValueError as exc:
        # A syntactically valid IP that is non-public must fail.  Hostnames are
        # resolved below and every returned address must be public.
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise exc
    else:
        return clean

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        resolved = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(
                hostname,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            ),
            timeout=3.0,
        )
    except (OSError, TimeoutError) as exc:
        raise ValueError(f"{purpose} hostname could not be resolved") from exc
    addresses = {str(item[4][0]).split("%", 1)[0] for item in resolved if item[4]}
    if not addresses:
        raise ValueError(f"{purpose} hostname did not resolve")
    for address in addresses:
        _reject_non_public_address(address)
    return clean


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
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS correlation_receipts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            idempotency_key TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'processing',
            created_by_actor_id UUID,
            match_count INT NOT NULL DEFAULT 0,
            case_id UUID,
            playbook_run_count INT NOT NULL DEFAULT 0,
            result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            CHECK (char_length(idempotency_key) BETWEEN 1 AND 128),
            CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
            CHECK (status IN ('processing', 'completed')),
            CHECK (jsonb_typeof(result_snapshot) = 'object'),
            UNIQUE (tenant_id, idempotency_key)
        )
        """
    )
    await pool.execute(
        "ALTER TABLE correlation_receipts ADD COLUMN IF NOT EXISTS result_snapshot "
        "JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


async def claim_correlation_receipt(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    idempotency_key: str,
    request_sha256: str,
    actor_id: str,
) -> tuple[UUID, bool]:
    """Claim a whole-operation idempotency receipt or resolve an exact replay."""
    await ensure_threat_schema(pool)
    row = await pool.fetchrow(
        """
        INSERT INTO correlation_receipts (
            tenant_id, idempotency_key, request_sha256, created_by_actor_id
        )
        VALUES ($1::uuid, $2, $3, $4::uuid)
        ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
        RETURNING id::text
        """,
        str(tenant_id),
        idempotency_key,
        request_sha256,
        actor_id,
    )
    if row is not None:
        return UUID(str(row["id"])), True
    existing = await pool.fetchrow(
        """
        SELECT id::text, request_sha256
        FROM correlation_receipts
        WHERE tenant_id = $1::uuid AND idempotency_key = $2
        """,
        str(tenant_id),
        idempotency_key,
    )
    if existing is None:
        raise RuntimeError("idempotent correlation receipt could not be resolved")
    if existing["request_sha256"] != request_sha256:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="idempotency key was already used with a different correlation request",
        )
    return UUID(str(existing["id"])), False


async def get_correlation_receipt_state(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    receipt_id: UUID,
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT status, result_snapshot
        FROM correlation_receipts
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        """,
        str(receipt_id),
        str(tenant_id),
    )


async def complete_correlation_receipt(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    receipt_id: UUID,
    match_count: int,
    case_id: UUID | None,
    playbook_run_count: int,
    result_snapshot: dict[str, Any],
    actor_id: str,
) -> bool:
    row = await pool.fetchrow(
        """
        WITH updated AS (
          UPDATE correlation_receipts
          SET status = 'completed', match_count = $3, case_id = $4::uuid,
              playbook_run_count = $5, result_snapshot = $6::jsonb,
              updated_at = NOW(), completed_at = COALESCE(completed_at, NOW())
          WHERE id = $1::uuid AND tenant_id = $2::uuid AND status = 'processing'
          RETURNING id::text
        ), audit_receipt AS (
          INSERT INTO audit_events (
            actor_user_id, tenant_id, action, resource_type, resource_id, details
          )
          SELECT $7, $2::uuid, 'siem.correlate', 'correlation', updated.id,
                 jsonb_build_object(
                   'match_count', $3,
                   'case_created', ($4::uuid IS NOT NULL),
                   'playbook_run_count', $5
                 )
          FROM updated
          RETURNING id
        )
        SELECT updated.id
        FROM updated CROSS JOIN audit_receipt
        """,
        str(receipt_id),
        str(tenant_id),
        match_count,
        str(case_id) if case_id else None,
        playbook_run_count,
        json.dumps(result_snapshot, default=str),
        actor_id,
    )
    return row is not None


# --- Abuse.ch IP blocklist fetch ---
async def fetch_abuse_ch_ips(*, timeout: float = 15.0) -> list[str]:
    limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, limits=limits) as client:
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
        # Keep only feed provenance needed for operations.  The complete STIX
        # document can contain descriptions, identities, or extension secrets.
        raw_labels = obj.get("labels")
        labels = raw_labels if isinstance(raw_labels, list) else []
        out.append(
            {
                "ip_address": ip,
                "raw_payload": {
                    "stix_id": str(obj.get("id") or "")[:255],
                    "valid_from": str(obj.get("valid_from") or "")[:64],
                    "labels": [str(label)[:64] for label in labels[:20]],
                },
            }
        )
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
    safe_url = await validate_outbound_url(collection_url, purpose="TAXII")
    headers = {"Accept": "application/taxii+json;version=2.1"}
    auth = (username, password) if username and password else None
    bounded_timeout = httpx.Timeout(min(max(timeout, 1.0), 30.0), connect=3.0, read=10.0)
    limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
    async with (
        httpx.AsyncClient(
            timeout=bounded_timeout,
            headers=headers,
            auth=auth,
            follow_redirects=False,
            limits=limits,
        ) as client,
        client.stream("GET", safe_url) as response,
    ):
        payload = await _read_taxii_response(response)
    try:
        bundle = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("TAXII response is not valid JSON") from exc
    objects = bundle.get("objects") if isinstance(bundle, dict) else None
    if not isinstance(objects, list):
        return []
    return parse_stix_ipv4_indicators(objects)


async def _read_taxii_response(response: httpx.Response) -> bytes:
    if 300 <= response.status_code < 400:
        raise ValueError("TAXII redirects are not allowed")
    response.raise_for_status()
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > _MAX_TAXII_RESPONSE_BYTES:
            raise ValueError("TAXII response exceeds 2 MiB")
        chunks.append(chunk)
    return b"".join(chunks)


# --- Lookup / list (JWT + membership for tenant scope) ---
async def lookup_ip(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    ip_address: str,
    tenant_id: UUID | None = None,
) -> list[dict[str, Any]]:
    if tenant_id is not None:
        await tenant_svc.require_tenant_access(
            pool,
            principal=user,
            tenant_id=tenant_id,
            required_scopes=frozenset({"threat-intel:read"}),
        )
    else:
        # Platform-only lookup contains no tenant rows, but is still human-only;
        # service principals must always exercise their tenant binding.
        require_user_principal(user)
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
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"threat-intel:read"}),
    )
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
