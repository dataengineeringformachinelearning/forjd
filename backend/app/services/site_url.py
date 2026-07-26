"""SSRF-safe public site URL validation ."""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Final
from urllib.parse import urlparse

ALLOWED_WEB_PORTS: Final[frozenset[int]] = frozenset({80, 443})


def normalized_domain(raw: str) -> str:
    candidate = raw.strip().lower().rstrip(".")
    parsed = urlparse(candidate if "://" in candidate else f"//{candidate}")
    host = parsed.hostname or ""
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("domain is not valid IDNA") from exc


def resolved_public_addresses(
    host: str,
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        literal = ipaddress.ip_address(host)
        return (literal,)
    except ValueError:
        pass
    try:
        records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("site domain could not be resolved") from exc
    addresses = tuple({ipaddress.ip_address(record[4][0]) for record in records})
    if not addresses:
        raise ValueError("site domain resolved without an address")
    return addresses


def validate_public_http_url(url: str, *, require_https: bool = True) -> str:
    """Validate a public http(s) URL and reject SSRF-capable targets."""
    parsed = urlparse(url.strip())
    allowed = {"https"} if require_https else {"http", "https"}
    if parsed.scheme not in allowed:
        message = "targets must use https" if require_https else "targets must use http or https"
        raise ValueError(message)
    if parsed.username or parsed.password:
        raise ValueError("targets cannot contain credentials")
    if not parsed.hostname:
        raise ValueError("target requires a hostname")
    if parsed.port is not None and parsed.port not in ALLOWED_WEB_PORTS:
        raise ValueError("target port is not allowed")

    host = normalized_domain(parsed.hostname)
    addresses = resolved_public_addresses(host)
    if any(not address.is_global for address in addresses):
        raise ValueError("target resolves to a non-public address")
    return parsed.geturl()


def validate_public_site_url(url: str, verified_domain: str) -> str:
    """Validate exact verified-origin ownership and reject SSRF-capable targets."""
    validated = validate_public_http_url(url, require_https=False)
    parsed = urlparse(validated)
    host = normalized_domain(parsed.hostname or "")
    expected = normalized_domain(verified_domain)
    if host != expected:
        raise ValueError("target must match the verified domain")
    return validated


def normalize_technology_name(raw: str) -> str:
    cleaned = re.sub(r"\s+", " ", raw.strip())[:255]
    return re.sub(r"[^a-z0-9+#.]+", "-", cleaned.lower()).strip("-")


def normalize_version(raw: object) -> str:
    if raw is None:
        return ""
    cleaned = re.sub(r"\s+", " ", str(raw).strip())[:128]
    if cleaned.lower() in {"unknown", "n/a", "none", "null", "latest"}:
        return ""
    return cleaned
