"""Firecrawl technology extraction client (from DEML; httpx, no Django)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

import asyncpg
import httpx

from app.core.auth import AuthUser
from app.core.config import settings
from app.services import tenants as tenant_svc
from app.services.site_url import (
    normalize_technology_name,
    normalize_version,
    validate_public_site_url,
)
from app.services.vulnerability_ledger import process_dual_stream_batch

logger = logging.getLogger("forjd.firecrawl")

MAX_TECHNOLOGIES_PER_SITE: Final[int] = 100
MAX_EVIDENCE_ITEMS: Final[int] = 8
MAX_EVIDENCE_LENGTH: Final[int] = 500


class FirecrawlTechnologyError(RuntimeError):
    """Raised when Firecrawl cannot return a trustworthy technology result."""


@dataclass(frozen=True)
class TechnologyEvidence:
    name: str
    normalized_name: str
    version: str
    confidence: float
    evidence: tuple[str, ...]


# --- Soft schema ---
async def ensure_tech_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS validated_sites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            domain TEXT NOT NULL,
            is_verified BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, domain)
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS web_technology_observations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            validated_site_id UUID NOT NULL REFERENCES validated_sites (id) ON DELETE CASCADE,
            source TEXT NOT NULL DEFAULT 'firecrawl',
            source_url TEXT NOT NULL,
            technology_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '',
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
            evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
            cpe_2_3 TEXT NOT NULL DEFAULT '',
            cve_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (validated_site_id, source, normalized_name, version)
        )
        """
    )


# --- Client ---
class FirecrawlTechnologyClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        min_confidence: float | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.FIRECRAWL_API_KEY
        self.base_url = (base_url or settings.FIRECRAWL_API_URL).rstrip("/")
        self.timeout_seconds = max(
            1, min(timeout_seconds if timeout_seconds is not None else 60, 300)
        )
        self.min_confidence = max(
            0.0,
            min(min_confidence if min_confidence is not None else 0.4, 1.0),
        )

    async def extract(self, url: str) -> list[TechnologyEvidence]:
        if not self.api_key:
            raise FirecrawlTechnologyError("Firecrawl API key is not configured")
        schema = {
            "type": "object",
            "properties": {
                "technologies": {
                    "type": "array",
                    "maxItems": MAX_TECHNOLOGIES_PER_SITE,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "version": {"type": ["string", "null"]},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "evidence": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["name", "confidence", "evidence"],
                    },
                }
            },
            "required": ["technologies"],
        }
        payload = {
            "url": url,
            "formats": [
                {
                    "type": "json",
                    "schema": schema,
                    "prompt": (
                        "Identify observable web technologies like Wappalyzer. "
                        "Only report a version with explicit evidence."
                    ),
                }
            ],
            "onlyMainContent": False,
            "timeout": min(self.timeout_seconds * 1000, 300_000),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds + 5, headers=headers
            ) as client:
                response = await client.post(f"{self.base_url}/v2/scrape", json=payload)
            if response.status_code != 200:
                raise FirecrawlTechnologyError(
                    f"Firecrawl HTTP {response.status_code}: {response.text[:400]}"
                )
            return self._parse(response.json())
        except FirecrawlTechnologyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirecrawlTechnologyError("Firecrawl request failed") from exc

    def _parse(self, payload: dict[str, Any]) -> list[TechnologyEvidence]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        structured = data.get("json") if isinstance(data, dict) else None
        if not isinstance(structured, dict):
            raise FirecrawlTechnologyError("Firecrawl response missing structured JSON")
        raw_items = structured.get("technologies")
        if not isinstance(raw_items, list):
            raise FirecrawlTechnologyError("Firecrawl response missing technologies")

        deduplicated: dict[tuple[str, str], TechnologyEvidence] = {}
        for raw in raw_items[:MAX_TECHNOLOGIES_PER_SITE]:
            if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
                continue
            name = re.sub(r"\s+", " ", raw["name"].strip())[:255]
            normalized = normalize_technology_name(name)
            if not normalized:
                continue
            try:
                confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
            except (TypeError, ValueError):
                continue
            raw_evidence = raw.get("evidence")
            evidence_items = raw_evidence if isinstance(raw_evidence, list) else []
            evidence = tuple(
                dict.fromkeys(
                    str(item).strip()[:MAX_EVIDENCE_LENGTH]
                    for item in evidence_items[:MAX_EVIDENCE_ITEMS]
                    if isinstance(item, str) and item.strip()
                )
            )
            if confidence < self.min_confidence or not evidence:
                continue
            version = normalize_version(raw.get("version"))
            candidate = TechnologyEvidence(name, normalized, version, confidence, evidence)
            key = (normalized, version)
            existing = deduplicated.get(key)
            if existing is None or candidate.confidence > existing.confidence:
                deduplicated[key] = candidate
        return sorted(deduplicated.values(), key=lambda i: (i.normalized_name, i.version))


# --- Persist + optional CVE enrichment ---
async def register_validated_site(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    domain: str,
    is_verified: bool = True,
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin"}),
    )
    await ensure_tech_schema(pool)
    from app.services.site_url import normalized_domain

    domain_n = normalized_domain(domain)
    row = await pool.fetchrow(
        """
        INSERT INTO validated_sites (tenant_id, domain, is_verified)
        VALUES ($1::uuid, $2, $3)
        ON CONFLICT (tenant_id, domain) DO UPDATE
          SET is_verified = EXCLUDED.is_verified
        RETURNING id::text, tenant_id::text, domain, is_verified, created_at
        """,
        str(tenant_id),
        domain_n,
        is_verified,
    )
    return dict(row)


async def enrich_site(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    site_id: UUID,
    url: str | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin"}),
    )
    await ensure_tech_schema(pool)
    site = await pool.fetchrow(
        """
        SELECT id::text, domain, is_verified
        FROM validated_sites
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        """,
        str(site_id),
        str(tenant_id),
    )
    if site is None:
        raise ValueError("validated site not found")
    if not site["is_verified"]:
        raise ValueError("site is not verified")
    target = url or f"https://{site['domain']}/"
    safe_url = validate_public_site_url(target, site["domain"])
    techs = await FirecrawlTechnologyClient().extract(safe_url)

    infra_batch = [
        {
            "tenant_id": str(tenant_id),
            "tech_name": t.name,
            "version": t.version,
            "url": safe_url,
        }
        for t in techs
    ]
    ledger = await process_dual_stream_batch(pool, infra_batch, [])
    enriched: dict[tuple[str, str], dict[str, Any]] = {}
    if not ledger.is_empty():
        for row in ledger.to_dicts():
            key = (
                normalize_technology_name(str(row.get("tech_name") or "")),
                normalize_version(row.get("version")),
            )
            bucket = enriched.setdefault(key, {"cpe_2_3": "", "cve_ids": set()})
            if row.get("cpe_2_3"):
                bucket["cpe_2_3"] = str(row["cpe_2_3"])
            if row.get("cve_id"):
                bucket["cve_ids"].add(str(row["cve_id"]))

    stored = 0
    for t in techs:
        match = enriched.get((t.normalized_name, t.version), {})
        cve_ids = sorted(str(x) for x in match.get("cve_ids", set()))
        await pool.execute(
            """
            INSERT INTO web_technology_observations (
                tenant_id, validated_site_id, source, source_url, technology_name,
                normalized_name, version, confidence, evidence, cpe_2_3, cve_ids
            )
            VALUES (
                $1::uuid, $2::uuid, 'firecrawl', $3, $4, $5, $6, $7, $8::jsonb, $9, $10::jsonb
            )
            ON CONFLICT (validated_site_id, source, normalized_name, version) DO UPDATE SET
                confidence = EXCLUDED.confidence,
                evidence = EXCLUDED.evidence,
                cpe_2_3 = EXCLUDED.cpe_2_3,
                cve_ids = EXCLUDED.cve_ids,
                last_seen_at = NOW()
            """,
            str(tenant_id),
            site["id"],
            safe_url,
            t.name,
            t.normalized_name,
            t.version,
            t.confidence,
            json.dumps(list(t.evidence)),
            str(match.get("cpe_2_3") or ""),
            json.dumps(cve_ids),
        )
        stored += 1
    return {
        "ok": True,
        "site_id": site["id"],
        "url": safe_url,
        "observed_count": stored,
        "technologies": [
            {
                "name": t.name,
                "normalized_name": t.normalized_name,
                "version": t.version,
                "confidence": t.confidence,
            }
            for t in techs
        ],
    }
