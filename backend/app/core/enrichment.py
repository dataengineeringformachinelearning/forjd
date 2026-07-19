"""User-Agent parsing for telemetry metadata."""

from __future__ import annotations

import re
from typing import Any


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
