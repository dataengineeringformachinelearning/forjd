"""UA parsing + IP geolocation enrichment ."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger("forjd.enrichment")

_CACHE_TTL_SECONDS = 60 * 60 * 24


# --- User-Agent parsing ---
def parse_user_agent(ua_string: str | None) -> dict[str, Any]:
    if not ua_string:
        return {
            "device_type": "Unknown",
            "os_name": "Unknown",
            "browser_name": "Unknown",
            "is_bot": False,
        }

    ua_lower = ua_string.lower()
    is_bot = bool(re.search(r"bot|spider|crawl|slurp|wget|curl", ua_lower))

    device_type = "Desktop"
    if is_bot:
        device_type = "Bot"
    elif re.search(r"tablet|ipad|playbook|silk", ua_lower):
        device_type = "Tablet"
    elif re.search(r"mobile|android|iphone|ipod|windows phone", ua_lower):
        device_type = "Mobile"

    os_name = "Unknown"
    if "windows" in ua_lower:
        os_name = "Windows"
    elif "mac os x" in ua_lower or "macintosh" in ua_lower:
        os_name = "Mac OS X"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "ios" in ua_lower or "iphone" in ua_lower or "ipad" in ua_lower:
        os_name = "iOS"
    elif "linux" in ua_lower:
        os_name = "Linux"

    browser_name = "Unknown"
    if "chrome" in ua_lower and "edg" not in ua_lower and "opr" not in ua_lower:
        browser_name = "Chrome"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        browser_name = "Safari"
    elif "firefox" in ua_lower:
        browser_name = "Firefox"
    elif "edg" in ua_lower:
        browser_name = "Edge"
    elif "opr" in ua_lower or "opera" in ua_lower:
        browser_name = "Opera"

    return {
        "device_type": device_type,
        "os_name": os_name,
        "browser_name": browser_name,
        "is_bot": is_bot,
    }


# --- IP enrichment (ipwho.is + optional Dragonfly cache) ---
async def get_ip_enrichment(
    ip_address: str,
    *,
    redis: Any | None = None,
) -> dict[str, str]:
    if not ip_address or ip_address in {"127.0.0.1", "localhost", "::1"}:
        return {"location": "Localhost", "asn": "N/A", "isp": "Local Network"}

    cache_key = f"ip_enrich:{ip_address}"
    client = redis
    try:
        if client is not None:
            cached = await client.get(cache_key)
            if cached:
                import json

                return json.loads(cached)
    except Exception:  # noqa: BLE001
        pass

    enrichment_data = {"location": "Unknown", "asn": "Unknown", "isp": "Unknown"}
    try:
        async with httpx.AsyncClient(timeout=3.0) as http:
            response = await http.get(f"https://ipwho.is/{ip_address}")
        if response.status_code == 200:
            data = response.json()
            if data.get("success") is True:
                country = data.get("country", "")
                city = data.get("city", "")
                enrichment_data["location"] = f"{city}, {country}".strip(", ")
                connection = data.get("connection") or {}
                enrichment_data["isp"] = str(connection.get("isp") or "Unknown")
                asn_num = connection.get("asn")
                enrichment_data["asn"] = f"AS{asn_num}" if asn_num else "Unknown"
    except Exception as exc:  # noqa: BLE001
        logger.warning("GeoIP lookup failed for %s: %s", ip_address, exc)

    try:
        if client is not None:
            import json

            await client.set(cache_key, json.dumps(enrichment_data), ex=_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass
    return enrichment_data


async def get_ip_enrichment_batch(
    ip_addresses: list[str | None],
    *,
    redis: Any | None = None,
) -> dict[str, dict[str, str]]:
    unique_ips = {ip for ip in ip_addresses if ip}
    result: dict[str, dict[str, str]] = {}
    for ip in unique_ips:
        result[ip] = await get_ip_enrichment(ip, redis=redis)
    return result
