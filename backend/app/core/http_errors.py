"""Client-safe HTTP error mapping — never leak internals to callers in production.

Unhandled 500s may include ``request_id`` for support join — never exception text
in production. ADR: ``docs/adr/0005-observability-correlation-first.md``.
Validation 422s keep ``loc``/``type``/``msg`` but drop request ``input`` bodies.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.request_context import request_id_var
from app.core.sanitize import sanitize_text

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


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return structured 422 without echoing request ``input`` payloads."""
    detail: list[dict[str, Any]] = []
    for err in exc.errors()[:50]:
        loc = [sanitize_text(str(part), max_length=64) for part in err.get("loc", ())[:16]]
        msg = sanitize_text(str(err.get("msg", "")), max_length=256) or GENERIC_INVALID_REQUEST
        err_type = sanitize_text(str(err.get("type", "value_error")), max_length=64)
        detail.append({"type": err_type or "value_error", "loc": loc, "msg": msg})
    if not detail:
        detail = [{"type": "value_error", "loc": [], "msg": GENERIC_INVALID_REQUEST}]
    return JSONResponse(status_code=422, content={"detail": detail})


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected errors; return a generic 500 body in production."""
    request_id = request_id_var.get()
    logger.exception(
        "unhandled exception method=%s path=%s error_type=%s",
        request.method,
        request.url.path,
        type(exc).__name__,
        extra={"request_id": request_id},
    )
    # Tag active Sentry scope so tracker events join JSON logs on request_id.
    if request_id and request_id != "-":
        try:
            import sentry_sdk

            sentry_sdk.set_tag("request_id", request_id)
        except Exception:  # noqa: BLE001 - optional SDK / not installed
            pass
    body: dict[str, Any] = {
        "detail": client_safe_detail(exc, fallback=GENERIC_REQUEST_FAILED),
    }
    # Support can join this id to JSON logs / Rollbar / Sentry without internals.
    if request_id and request_id != "-":
        body["request_id"] = request_id
    return JSONResponse(status_code=500, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """Install production-safe handlers on the FastAPI app."""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


def error_payload(detail: str, **extra: Any) -> dict[str, Any]:
    """Build a minimal JSON error body."""
    body: dict[str, Any] = {"detail": detail}
    body.update(extra)
    return body
