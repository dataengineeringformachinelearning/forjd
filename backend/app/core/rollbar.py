"""Rollbar error reporting — enabled only when ROLLBAR_ACCESS_TOKEN is set."""

from __future__ import annotations

import logging

import rollbar
from fastapi import FastAPI
from rollbar.contrib.fastapi import ReporterMiddleware as RollbarMiddleware

from app.core.config import settings

logger = logging.getLogger("forjd.rollbar")


def configure_rollbar(app: FastAPI) -> bool:
    """Init Rollbar and attach middleware. Returns True if enabled."""
    token = settings.ROLLBAR_ACCESS_TOKEN.strip()
    if not token:
        logger.info("rollbar disabled (no ROLLBAR_ACCESS_TOKEN)")
        return False

    rollbar.init(
        token,
        environment=settings.ENVIRONMENT,
        handler="async",
        code_version=settings.PROJECT_VERSION,
    )
    # First middleware = outermost; Rollbar docs want it registered first.
    app.add_middleware(RollbarMiddleware)
    logger.info("rollbar enabled env=%s", settings.ENVIRONMENT)
    return True
