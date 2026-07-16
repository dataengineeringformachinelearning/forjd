"""Engine client — prefers out-of-process HTTP (`ENGINE_URL`), falls back to in-process PyO3."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("forjd.engine")

_pyo3 = None
_import_error: str | None = None

try:
    import forjd_engine as _pyo3  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - build/env dependent
    _import_error = str(exc)
    logger.warning("forjd_engine PyO3 extension unavailable: %s", exc)


def _http_configured() -> bool:
    return bool(settings.ENGINE_URL.strip())


def engine_available() -> bool:
    return _http_configured() or _pyo3 is not None


def engine_status() -> dict[str, Any]:
    if _http_configured():
        return {
            "ok": True,
            "mode": "http",
            "url": settings.ENGINE_URL.rstrip("/"),
            "auth": bool(settings.ENGINE_API_TOKEN),
        }
    if _pyo3 is None:
        return {"ok": False, "mode": "none", "error": _import_error or "not loaded"}
    return {
        "ok": True,
        "mode": "pyo3",
        "version": getattr(_pyo3, "engine_version", lambda: "unknown")(),
    }


def _auth_headers() -> dict[str, str]:
    token = settings.ENGINE_API_TOKEN.strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}", "X-Engine-Token": token}


async def _http_json(method: str, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
    base = settings.ENGINE_URL.rstrip("/")
    timeout = httpx.Timeout(settings.ENGINE_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(base_url=base, timeout=timeout, headers=_auth_headers()) as client:
        response = await client.request(method, path, json=json_body)
        if response.status_code >= 400:
            detail: str
            try:
                detail = str(response.json().get("error") or response.text)
            except Exception:
                detail = response.text
            raise RuntimeError(f"engine HTTP {response.status_code}: {detail}")
        return response.json()


async def process_event(event: dict[str, Any]) -> dict[str, Any]:
    if _http_configured():
        return dict(await _http_json("POST", "/v1/process", json_body=event))
    if _pyo3 is None:
        raise RuntimeError(f"forjd_engine not available: {_import_error}")
    return dict(_pyo3.process_event(event))


async def summarize_values(values: list[float]) -> dict[str, Any]:
    if _http_configured():
        return dict(await _http_json("POST", "/v1/summarize", json_body={"values": values}))
    if _pyo3 is None:
        raise RuntimeError(f"forjd_engine not available: {_import_error}")
    result = _pyo3.summarize_values(values)
    if hasattr(result, "as_dict"):
        return dict(result.as_dict())
    return {
        "count": result.count,
        "sum": result.sum,
        "mean": result.mean,
        "min": getattr(result, "min", None),
        "max": getattr(result, "max", None),
        "parquet_bytes": result.parquet_bytes,
    }


async def remote_version() -> dict[str, Any] | None:
    """Probe HTTP engine `/v1/version` when `ENGINE_URL` is set."""
    if not _http_configured():
        return None
    try:
        return dict(await _http_json("GET", "/v1/version"))
    except Exception as exc:
        logger.warning("engine version probe failed: %s", exc)
        return {"ok": False, "error": str(exc)}
