"""Thin, gated clients for the security-domain add-ons.

Every entrypoint checks ``addon_enabled(...)`` first and raises ``AddonDisabled``
if the add-on is off, so callers cannot accidentally reach a disabled service.
Network/tool calls are best-effort and never raise on remote failure — they
return structured error dicts so the vulnerability/threat pipelines stay up.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.addons.registry import addon_enabled, get_addon
from app.core.config import settings


class AddonDisabled(RuntimeError):
    """Raised when a caller uses an add-on that is not enabled in settings."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"add-on {slug!r} is disabled (enable via FORJD_ADDONS)")
        self.slug = slug


def _require(slug: str) -> None:
    if not addon_enabled(slug):
        raise AddonDisabled(slug)


# --- OSV.dev (vulnerability advisories) ---
async def osv_query(
    *, name: str, version: str, ecosystem: str = "PyPI", timeout: float = 10.0
) -> dict[str, Any]:
    """Query OSV.dev for advisories affecting a package/version."""
    _require("osv-dev")
    base = str(settings.OSV_API_URL or "https://api.osv.dev").rstrip("/")
    payload = {"version": version, "package": {"name": name, "ecosystem": ecosystem}}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base}/v1/query", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc), "vulns": []}
    vulns = data.get("vulns") or []
    return {
        "ok": True,
        "package": name,
        "version": version,
        "ecosystem": ecosystem,
        "count": len(vulns),
        "vulns": [
            {"id": v.get("id"), "summary": v.get("summary"), "aliases": v.get("aliases", [])}
            for v in vulns
        ],
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
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get("https://honeydb.io/api/bad-hosts", headers=headers)
            resp.raise_for_status()
            hosts = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc), "hosts": []}
    return {"ok": True, "count": len(hosts), "hosts": hosts}


# --- go-cve-dictionary (local CVE mirror) ---
async def cve_lookup(*, cve_id: str, timeout: float = 10.0) -> dict[str, Any]:
    """Resolve a CVE id against a self-hosted go-cve-dictionary service."""
    _require("go-cve-dictionary")
    base = str(settings.GO_CVE_DICTIONARY_URL or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "error": "GO_CVE_DICTIONARY_URL not set"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base}/cves/{cve_id}")
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "cve_id": cve_id, "record": data}


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
        return {"ok": False, "error": str(exc)}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", "replace"),
        "stderr": stderr.decode("utf-8", "replace"),
    }


async def osv_scanner_scan(*, path: str, timeout: float = 120.0) -> dict[str, Any]:
    """Run osv-scanner against a lockfile/SBOM/directory and return JSON output."""
    return await _run_tool(
        "osv-scanner", "osv-scanner", ["--format", "json", "--recursive", path], timeout
    )


async def nuclei_scan(*, target: str, timeout: float = 300.0) -> dict[str, Any]:
    """Run a nuclei template scan against a target URL (JSONL output)."""
    return await _run_tool("nuclei", "nuclei", ["-u", target, "-jsonl", "-silent"], timeout)
