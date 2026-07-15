"""Minimal structured logging — JSON lines to stdout, stdlib only."""

from __future__ import annotations

import logging
import sys


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage().replace('"', '\\"')
        return (
            f'{{"time":"{self.formatTime(record, self.datefmt)}",'
            f'"level":"{record.levelname}",'
            f'"logger":"{record.name}",'
            f'"message":"{message}"}}'
        )


def configure_logging(*, debug: bool = False) -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z"))

    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.addHandler(handler)

    # Keep noisy third-party loggers quieter in normal runs
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
