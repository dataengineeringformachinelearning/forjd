"""Thin wrapper around the Rust `forjd_engine` extension (PyO3)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("forjd.engine")

_engine = None
_import_error: str | None = None

try:
    import forjd_engine as _engine  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - build/env dependent
    _import_error = str(exc)
    logger.warning("forjd_engine unavailable: %s", exc)


def engine_available() -> bool:
    return _engine is not None


def engine_status() -> dict[str, Any]:
    if _engine is None:
        return {"ok": False, "error": _import_error or "not loaded"}
    return {
        "ok": True,
        "version": getattr(_engine, "engine_version", lambda: "unknown")(),
    }


def process_event(event: dict[str, Any]) -> dict[str, Any]:
    if _engine is None:
        raise RuntimeError(f"forjd_engine not available: {_import_error}")
    return dict(_engine.process_event(event))


def summarize_values(values: list[float]) -> dict[str, Any]:
    if _engine is None:
        raise RuntimeError(f"forjd_engine not available: {_import_error}")
    result = _engine.summarize_values(values)
    if hasattr(result, "as_dict"):
        return dict(result.as_dict())
    return {
        "count": result.count,
        "sum": result.sum,
        "mean": result.mean,
        "parquet_bytes": result.parquet_bytes,
    }
