"""Certificate Transparency (crt.sh) subdomain fetcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.services.fetchers.base import Fetcher


# --- Query / result DTOs ---
@dataclass(slots=True, frozen=True)
class CrtShQuery:
    domain: str
    timeout: float = 20.0


@dataclass(slots=True, frozen=True)
class CrtShData:
    domain: str
    subdomains: list[str]


# --- Fetcher ---
class CrtShFetcher(Fetcher[CrtShQuery, list[dict[str, Any]], CrtShData]):
    name = "crt.sh"

    def transform_query(self, params: dict[str, Any]) -> CrtShQuery:
        domain = str(params.get("domain") or "").strip().lower().lstrip(".")
        if len(domain) < 3 or "." not in domain:
            raise ValueError("invalid domain")
        timeout = float(params.get("timeout") or 20.0)
        return CrtShQuery(domain=domain, timeout=max(1.0, min(timeout, 60.0)))

    async def aextract(self, query: CrtShQuery) -> list[dict[str, Any]]:
        url = f"https://crt.sh/?q={query.domain}&output=json"
        async with httpx.AsyncClient(timeout=query.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, list):
            return []
        return [row for row in payload if isinstance(row, dict)]

    def transform_data(self, query: CrtShQuery, raw: list[dict[str, Any]]) -> CrtShData:
        subdomains: set[str] = set()
        needle = query.domain
        for entry in raw:
            name_value = str(entry.get("name_value") or "")
            for name in name_value.split("\n"):
                name = name.strip().lower()
                if name.endswith(needle) and "*" not in name:
                    subdomains.add(name)
        return CrtShData(domain=query.domain, subdomains=sorted(subdomains))
