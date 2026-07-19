"""Structured JSON logging with request correlation, using the stdlib only."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from app.core.request_context import log_context

_STANDARD_LOG_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **log_context(),
        }
        for key in ("http_method", "http_path", "http_status", "duration_ms"):
            if key in record.__dict__:
                payload[key] = record.__dict__[key]
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Preserve intentional structured extras while excluding stdlib internals.
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _STANDARD_LOG_FIELDS or key in payload:
                continue
            if _json_scalar(value):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_scalar(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool | list | dict)


def configure_logging(*, debug: bool = False) -> None:
    root = logging.getLogger()
    formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z")
    if root.handlers:
        # Uvicorn commonly installs handlers before application lifespan. Reuse
        # those streams but still guarantee one-line JSON rather than silently
        # leaving production on an unrelated default formatter.
        for existing in root.handlers:
            existing.setFormatter(formatter)
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root.addHandler(handler)

    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Keep noisy third-party loggers quieter in normal runs
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
