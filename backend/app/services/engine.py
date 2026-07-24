"""Engine client — prefers out-of-process HTTP (`ENGINE_URL`), falls back to in-process PyO3."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("forjd.engine")

_pyo3 = None
_import_error: str | None = None
_async_client: httpx.AsyncClient | None = None
_sync_client: httpx.Client | None = None

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


def _needs_ipv6_bind(base: str) -> bool:
    host = base.split("://", 1)[-1].split("/", 1)[0].split(":")[0].lower()
    return host.endswith(".internal") or host.endswith(".flycast")


# --- Shared HTTP clients (keep-alive; closed on app shutdown) ---
def _ensure_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is not None and not _async_client.is_closed:
        return _async_client
    base = settings.ENGINE_URL.rstrip("/")
    transport = None
    if _needs_ipv6_bind(base):
        transport = httpx.AsyncHTTPTransport(local_address="::")
    _async_client = httpx.AsyncClient(
        base_url=base,
        timeout=httpx.Timeout(settings.ENGINE_TIMEOUT_SECONDS),
        headers=_auth_headers(),
        transport=transport,
    )
    return _async_client


def _ensure_sync_client() -> httpx.Client:
    global _sync_client
    if _sync_client is not None and not _sync_client.is_closed:
        return _sync_client
    base = settings.ENGINE_URL.rstrip("/")
    transport = None
    if _needs_ipv6_bind(base):
        transport = httpx.HTTPTransport(local_address="::")
    _sync_client = httpx.Client(
        base_url=base,
        timeout=httpx.Timeout(settings.ENGINE_TIMEOUT_SECONDS),
        headers=_auth_headers(),
        transport=transport,
    )
    return _sync_client


async def close_engine_clients() -> None:
    """Lifespan shutdown — drop keep-alive pools."""
    global _async_client, _sync_client
    if _async_client is not None and not _async_client.is_closed:
        await _async_client.aclose()
    _async_client = None
    if _sync_client is not None and not _sync_client.is_closed:
        _sync_client.close()
    _sync_client = None


async def _http_json(method: str, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
    client = _ensure_async_client()
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


# --- Sealed-metadata pipeline (sync; used from the Prefect hot path) ---
def run_sealed_pipeline_sync(
    events: list[dict[str, Any]],
    *,
    steps: list[str] | None = None,
    params: dict[str, Any] | None = None,
    tags: dict[str, Any] | None = None,
    projection_name: str = "sealed.default",
    workflow_id: str | None = None,
) -> dict[str, Any] | None:
    """Run Rust sealed pipeline via PyO3 or sync HTTP. Returns None if unavailable."""
    steps = steps or ["rollup", "size_anomaly"]
    params = params or {}
    tags = tags or {}

    if _pyo3 is not None and hasattr(_pyo3, "run_sealed_pipeline"):
        try:
            out = _pyo3.run_sealed_pipeline(
                events,
                steps=steps,
                params=params,
                tags=tags,
                projection_name=projection_name,
                workflow_id=workflow_id,
            )
            return dict(out) if not isinstance(out, dict) else out
        except Exception as exc:  # noqa: BLE001
            logger.warning("rust sealed pipeline (pyo3) failed: %s", exc)

    if _http_configured():
        try:
            client = _ensure_sync_client()
            response = client.post(
                "/v1/sealed/pipeline",
                json={
                    "events": events,
                    "steps": steps,
                    "params": params,
                    "tags": tags,
                    "projection_name": projection_name,
                    "workflow_id": workflow_id,
                },
            )
            if response.status_code >= 400:
                logger.warning(
                    "rust sealed pipeline HTTP %s: %s",
                    response.status_code,
                    response.text[:200],
                )
                return None
            return dict(response.json())
        except Exception as exc:  # noqa: BLE001
            logger.warning("rust sealed pipeline (http) failed: %s", exc)
    return None
