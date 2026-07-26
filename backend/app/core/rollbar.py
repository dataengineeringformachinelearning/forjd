"""Rollbar error reporting — enabled only when ROLLBAR_ACCESS_TOKEN is set.

Deep-scrubs payloads via ``scrub_for_logs`` (parity with Sentry ``before_send``).
ADR: docs/adr/0017-secrets-and-sensitive-data.md
"""

from __future__ import annotations

import logging
from typing import Any

import rollbar
from fastapi import FastAPI
from rollbar.contrib.fastapi import ReporterMiddleware as RollbarMiddleware

from app.core.config import settings

logger = logging.getLogger("forjd.rollbar")

# Extend Rollbar defaults — init replaces scrub_fields entirely when passed.
_EXTRA_SCRUB_FIELDS = (
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-engine-token",
    "ciphertext",
    "sealed_payload",
    "private_key",
    "access_token",
    "refresh_token",
    "provision_token",
    "jwt_secret",
    "postgres_dsn",
    "redis_url",
    "database_url",
    "hf_token",
)


def _install_deep_scrub() -> None:
    """Wrap payload build so message/exception values are scrubbed, not only keys."""
    from app.core.sanitize import scrub_for_logs

    original = rollbar._build_payload

    def _build_payload_scrubbed(data: dict[str, Any]) -> dict[str, Any]:
        scrubbed = scrub_for_logs(data)
        if not isinstance(scrubbed, dict):
            scrubbed = {"body": {"message": {"body": "[Filtered]"}}}
        # access_token for the Rollbar API is added by ``original`` after this.
        return original(scrubbed)

    rollbar._build_payload = _build_payload_scrubbed  # type: ignore[method-assign]


def configure_rollbar(app: FastAPI) -> bool:
    """Init Rollbar and attach middleware. Returns True if enabled."""
    token = settings.ROLLBAR_ACCESS_TOKEN.strip()
    if not token:
        logger.info("rollbar disabled (no ROLLBAR_ACCESS_TOKEN)")
        return False

    scrub_fields = list(dict.fromkeys([*rollbar.SETTINGS["scrub_fields"], *_EXTRA_SCRUB_FIELDS]))
    rollbar.init(
        token,
        environment=settings.ENVIRONMENT,
        handler="async",
        code_version=settings.PROJECT_VERSION,
        scrub_fields=scrub_fields,
    )
    _install_deep_scrub()
    # First middleware = outermost; Rollbar docs want it registered first.
    app.add_middleware(RollbarMiddleware)
    logger.info("rollbar enabled env=%s", settings.ENVIRONMENT)
    return True
