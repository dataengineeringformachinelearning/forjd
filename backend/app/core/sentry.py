"""Sentry error tracking — enabled only when SENTRY_DSN is set.

Optional dependency: install with ``uv sync --group sentry``. When the DSN is
empty or the SDK is not installed, this is a no-op so slim images and local dev
run unchanged.
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger("forjd.sentry")


def configure_sentry() -> bool:
    """Initialise Sentry if a DSN is configured. Returns True if enabled."""
    dsn = settings.SENTRY_DSN.strip()
    if not dsn:
        logger.info("sentry disabled (no SENTRY_DSN)")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ModuleNotFoundError:
        logger.warning("SENTRY_DSN set but sentry-sdk not installed (uv sync --group sentry)")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=(settings.SENTRY_ENVIRONMENT or settings.ENVIRONMENT).strip(),
        release=f"forjd@{settings.PROJECT_VERSION}",
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    logger.info("sentry enabled env=%s", settings.SENTRY_ENVIRONMENT or settings.ENVIRONMENT)
    return True
