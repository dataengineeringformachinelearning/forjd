"""Structured extras for supervised worker ticks (stdout JSON only — no second metrics stack).

ADR: ``docs/adr/0005-observability-correlation-first.md``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def worker_tick(
    logger: logging.Logger,
    worker: str,
    *,
    level: int = logging.INFO,
) -> Iterator[dict[str, Any]]:
    """Time a worker tick and emit a structured completion line.

    Usage::

        with worker_tick(logger, "analytics-rollup") as tick:
            tick["tenants"] = await do_work()
    """
    started = time.perf_counter()
    extras: dict[str, Any] = {"worker": worker, "outcome": "ok"}
    try:
        yield extras
    except Exception:
        extras["outcome"] = "error"
        extras["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
        logger.exception("worker_tick", extra=extras)
        raise
    extras.setdefault("outcome", "ok")
    extras["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
    logger.log(level, "worker_tick", extra=extras)
