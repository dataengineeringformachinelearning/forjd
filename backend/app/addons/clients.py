"""Thin, gated clients for the security-domain add-ons.

Every entrypoint checks ``addon_enabled(...)`` first and raises ``AddonDisabled``
if the add-on is off, so callers cannot accidentally reach a disabled service.
Network/tool calls are best-effort and never raise on remote failure — they
return structured error dicts so the vulnerability/threat pipelines stay up.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.addons.registry import addon_enabled, get_addon
from app.core.config import settings
from app.core.outbound_http import (
    OutboundHttpError,
    expect_dict,
    expect_list,
    expect_list_of_dicts,
    request_json,
)
from app.core.sanitize import sanitize_external, sanitize_text


class AddonDisabled(RuntimeError):
    """Raised when a caller uses an add-on that is not enabled in settings."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"add-on {slug!r} is disabled (enable via FORJD_ADDONS)")
        self.slug = slug


def _require(slug: str) -> None:
    if not addon_enabled(slug):
        raise AddonDisabled(slug)


def _soft_error(exc: BaseException, *, empty_key: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": sanitize_text(str(exc), max_length=256),
        empty_key: [],
    }


# --- OSV.dev (vulnerability advisories) ---
async def osv_query(
    *, name: str, version: str, ecosystem: str = "PyPI", timeout: float = 10.0
) -> dict[str, Any]:
    """Query OSV.dev for advisories affecting a package/version."""
    _require("osv-dev")
    base = str(settings.OSV_API_URL or "https://api.osv.dev").rstrip("/")
    payload = {"version": version, "package": {"name": name, "ecosystem": ecosystem}}
    try:
        _status, data = await request_json(
            "POST",
            f"{base}/v1/query",
            timeout=timeout,
            json_body=payload,
        )
    except (OutboundHttpError, OSError) as exc:
        return _soft_error(exc, empty_key="vulns")
    body = expect_dict(data)
    vulns_raw = expect_list_of_dicts(body.get("vulns"), max_items=200)
    vulns = [
        {
            "id": sanitize_text(str(v.get("id") or ""), max_length=128),
            "summary": sanitize_text(str(v.get("summary") or ""), max_length=512),
            "aliases": [
                sanitize_text(str(a), max_length=128) for a in expect_list(v.get("aliases"))[:32]
            ],
        }
        for v in vulns_raw
    ]
    return {
        "ok": True,
        "package": sanitize_text(name, max_length=256),
        "version": sanitize_text(version, max_length=64),
        "ecosystem": sanitize_text(ecosystem, max_length=64),
        "count": len(vulns),
        "vulns": vulns,
    }


# --- HoneyDB (honeypot threat intel) ---
async def honeydb_bad_hosts(*, timeout: float = 10.0) -> dict[str, Any]:
    """Fetch the HoneyDB bad-hosts feed (requires API id + key)."""
    _require("honeydb")
    api_id = str(settings.HONEYDB_API_ID or "").strip()
    api_key = str(settings.HONEYDB_API_KEY or "").strip()
    if not (api_id and api_key):
        return {"ok": False, "error": "HONEYDB_API_ID / HONEYDB_API_KEY not set", "hosts": []}
    headers = {"X-HoneyDb-ApiId": api_id, "X-HoneyDb-ApiKey": api_key}
    try:
        _status, hosts = await request_json(
            "GET",
            "https://honeydb.io/api/bad-hosts",
            timeout=timeout,
            headers=headers,
        )
    except (OutboundHttpError, OSError) as exc:
        return _soft_error(exc, empty_key="hosts")
    cleaned = sanitize_external(expect_list(hosts), max_list=500, max_str=256)
    if not isinstance(cleaned, list):
        cleaned = []
    return {"ok": True, "count": len(cleaned), "hosts": cleaned}


# --- go-cve-dictionary (local CVE mirror) ---
async def cve_lookup(*, cve_id: str, timeout: float = 10.0) -> dict[str, Any]:
    """Resolve a CVE id against a self-hosted go-cve-dictionary service."""
    _require("go-cve-dictionary")
    base = str(settings.GO_CVE_DICTIONARY_URL or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "error": "GO_CVE_DICTIONARY_URL not set"}
    try:
        _status, data = await request_json(
            "GET",
            f"{base}/cves/{cve_id}",
            timeout=timeout,
        )
    except (OutboundHttpError, OSError) as exc:
        return {
            "ok": False,
            "error": sanitize_text(str(exc), max_length=256),
        }
    return {
        "ok": True,
        "cve_id": sanitize_text(cve_id, max_length=64),
        "record": sanitize_external(expect_dict(data)),
    }


# --- External tools (nuclei / osv-scanner) ---
async def _run_tool(slug: str, binary: str, args: list[str], timeout: float) -> dict[str, Any]:
    _require(slug)
    addon = get_addon(slug)
    if addon is None or not addon.available():
        return {"ok": False, "error": f"{binary} not found on PATH"}
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (OSError, TimeoutError) as exc:
        return {"ok": False, "error": sanitize_text(str(exc), max_length=256)}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": sanitize_text(stdout.decode("utf-8", "replace"), max_length=16_384),
        "stderr": sanitize_text(stderr.decode("utf-8", "replace"), max_length=4_096),
    }


async def osv_scanner_scan(*, path: str, timeout: float = 120.0) -> dict[str, Any]:
    """Run osv-scanner against a lockfile/SBOM/directory and return JSON output."""
    return await _run_tool(
        "osv-scanner", "osv-scanner", ["--format", "json", "--recursive", path], timeout
    )


async def nuclei_scan(*, target: str, timeout: float = 300.0) -> dict[str, Any]:
    """Run a nuclei template scan against a target URL (JSONL output)."""
    return await _run_tool("nuclei", "nuclei", ["-u", target, "-jsonl", "-silent"], timeout)
