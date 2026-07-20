"""Shared Prefect soft-fail: run locally when the Prefect API is unreachable."""

from __future__ import annotations

import os
from collections.abc import Callable
from threading import Lock
from time import monotonic
from typing import Any

import httpx
from prefect.client.orchestration import get_client

from app.core.config import settings

_PREFECT_HEALTH_CACHE_SECONDS = 5.0
_PREFECT_HEALTH_TIMEOUT_SECONDS = 0.5
_health_lock = Lock()
_health_checked_at = 0.0
_health_error: Exception | None = None


def _configured_prefect_url() -> str:
    """Effective Prefect URL — raw env wins because pydantic ignores empty env.

    Production sets ``PREFECT_API_URL=''`` (no orchestrator); ``env_ignore_empty``
    would silently substitute the localhost default, so read the env directly.
    """
    raw = os.environ.get("PREFECT_API_URL")
    if raw is not None:
        return raw.strip()
    return (settings.PREFECT_API_URL or "").strip()


def _prefect_api_error() -> Exception | None:
    """Probe orchestration before business work so fallback cannot duplicate it."""
    global _health_checked_at, _health_error
    if not _configured_prefect_url():
        # No orchestrator configured (production default): deterministic local
        # fallback. Probing would boot Prefect's ephemeral server, whose import
        # chain (docket → key_value.aio) breaks under the Pathway beartype pin.
        return httpx.ConnectError("PREFECT_API_URL is not configured")
    now = monotonic()
    with _health_lock:
        if now - _health_checked_at < _PREFECT_HEALTH_CACHE_SECONDS:
            return _health_error
        try:
            with get_client(
                sync_client=True,
                httpx_settings={"timeout": _PREFECT_HEALTH_TIMEOUT_SECONDS},
            ) as client:
                error = client.api_healthcheck()
        except Exception as exc:  # noqa: BLE001 - configuration errors must propagate
            error = exc
        _health_checked_at = monotonic()
        _health_error = error
        return error


def _orchestration_is_unavailable(exc: Exception) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 425, 429} or exc.response.status_code >= 500
    return False


# --- Soft-fail wrapper ---
def run_with_local_fallback[T](
    flow_fn: Callable[..., T],
    *args: Any,
    fallback: Callable[[Exception], T],
    **kwargs: Any,
) -> T:
    """Use local execution only when a preflight proves Prefect unavailable.

    Once the flow starts, every exception is propagated. Retrying the complete
    fallback after a processor or add-on hook partially ran would execute those
    side effects twice.
    """
    orchestration_error = _prefect_api_error()
    if orchestration_error is not None:
        if _orchestration_is_unavailable(orchestration_error):
            return fallback(orchestration_error)
        raise orchestration_error
    return flow_fn(*args, **kwargs)
