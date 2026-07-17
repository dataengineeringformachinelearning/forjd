"""Shared Prefect soft-fail: run locally when the Prefect API is unreachable."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


# --- Soft-fail wrapper ---
def run_with_local_fallback[T](
    flow_fn: Callable[..., T],
    *args: Any,
    fallback: Callable[[Exception], T],
    **kwargs: Any,
) -> T:
    """Invoke a Prefect `@flow`; on any client/API error, use `fallback(exc)`."""
    try:
        return flow_fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — intentional soft-fail boundary
        return fallback(exc)
