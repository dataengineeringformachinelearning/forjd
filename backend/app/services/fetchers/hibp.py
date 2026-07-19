"""Have I Been Pwned breach-account fetcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.services.fetchers.base import Fetcher


# --- Query / result DTOs ---
@dataclass(slots=True, frozen=True)
class HibpQuery:
    email: str
    api_key: str = ""
    timeout: float = 15.0


@dataclass(slots=True, frozen=True)
class HibpData:
    breaches: list[Any]
    not_found: bool = False
    http_status: int | None = None


class HibpExtractError(RuntimeError):
    """Non-404 HIBP HTTP failure with status preserved for callers."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"http_{status_code}")


# --- Fetcher ---
class HibpFetcher(Fetcher[HibpQuery, HibpData, HibpData]):
    name = "hibp"

    def transform_query(self, params: dict[str, Any]) -> HibpQuery:
        email = str(params.get("email") or "").strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("invalid email")
        api_key = str(params.get("api_key") or settings.HIBP_API_KEY or "").strip()
        timeout = float(params.get("timeout") or 15.0)
        return HibpQuery(email=email, api_key=api_key, timeout=max(1.0, min(timeout, 60.0)))

    async def aextract(self, query: HibpQuery) -> HibpData:
        headers = {"User-Agent": "FORJD-OSINT"}
        if query.api_key:
            headers["hibp-api-key"] = query.api_key
        url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{query.email}"
        async with httpx.AsyncClient(timeout=query.timeout, headers=headers) as client:
            response = await client.get(url)
        if response.status_code == 404:
            return HibpData(breaches=[], not_found=True, http_status=404)
        if response.status_code != 200:
            raise HibpExtractError(response.status_code)
        payload = response.json()
        breaches = payload if isinstance(payload, list) else []
        return HibpData(breaches=breaches, http_status=200)

    def transform_data(self, query: HibpQuery, raw: HibpData) -> HibpData:
        _ = query
        return raw
