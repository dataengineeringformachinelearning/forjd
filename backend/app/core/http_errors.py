"""Client-safe HTTP error mapping — never leak internals to callers in production."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger("forjd.http_errors")

# --- Generic client-facing copy ---
GENERIC_REQUEST_FAILED = "request failed"
GENERIC_INVALID_REQUEST = "invalid request"


def expose_error_details() -> bool:
    """True when clients may see raw exception text (local DEBUG only)."""
    return bool(settings.DEBUG) and not settings.is_production


def client_safe_detail(
    exc: BaseException,
    *,
    fallback: str = GENERIC_REQUEST_FAILED,
) -> str:
    """Map an unexpected failure to a client-safe detail string."""
    if expose_error_details():
        text = str(exc).strip()
        return text or fallback
    return fallback


def intentional_detail(
    exc: BaseException,
    *,
    fallback: str = GENERIC_INVALID_REQUEST,
) -> str:
    """Pass through authored validation messages; never empty."""
    text = str(exc).strip()
    return text or fallback


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected errors; return a generic 500 body in production."""
    logger.exception(
        "unhandled exception method=%s path=%s error_type=%s",
        request.method,
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": client_safe_detail(exc, fallback=GENERIC_REQUEST_FAILED)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Install production-safe handlers on the FastAPI app."""
    app.add_exception_handler(Exception, unhandled_exception_handler)


def error_payload(detail: str, **extra: Any) -> dict[str, Any]:
    """Build a minimal JSON error body."""
    body: dict[str, Any] = {"detail": detail}
    body.update(extra)
    return body
