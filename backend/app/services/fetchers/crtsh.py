"""Certificate Transparency (crt.sh) subdomain fetcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.outbound_http import expect_list_of_dicts, request_json
from app.core.sanitize import sanitize_label
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
        _status, payload = await request_json("GET", url, timeout=query.timeout)
        return expect_list_of_dicts(payload, max_items=2_000)

    def transform_data(self, query: CrtShQuery, raw: list[dict[str, Any]]) -> CrtShData:
        subdomains: set[str] = set()
        needle = query.domain
        for entry in raw:
            name_value = str(entry.get("name_value") or "")
            for name in name_value.split("\n"):
                name = sanitize_label(name.lower(), max_length=253)
                if name.endswith(needle) and "*" not in name:
                    subdomains.add(name)
        return CrtShData(
            domain=sanitize_label(query.domain, max_length=253),
            subdomains=sorted(subdomains)[:500],
        )
