"""Per-request correlation context for logs and response headers."""

from __future__ import annotations

import contextvars
import logging
import re
import time
from typing import Any
from uuid import uuid4

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
principal_kind_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "principal_kind", default="-"
)
principal_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("principal_id", default="-")
tenant_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="-")

logger = logging.getLogger("forjd.http")


def valid_request_id(value: str | None) -> bool:
    """Return whether a caller-supplied correlation ID is safe to echo and log."""
    return bool(value and _REQUEST_ID_RE.fullmatch(value))


def bind_principal_context(
    *, principal_kind: str, principal_id: str, tenant_id: str | None = None
) -> None:
    """Attach an authenticated principal to the current request log context."""
    principal_kind_var.set(principal_kind)
    principal_id_var.set(principal_id)
    if tenant_id:
        tenant_id_var.set(tenant_id)


def log_context() -> dict[str, str]:
    """Return non-secret request context for structured log records."""
    return {
        "request_id": request_id_var.get(),
        "principal_kind": principal_kind_var.get(),
        "principal_id": principal_id_var.get(),
        "tenant_id": tenant_id_var.get(),
    }


class RequestContextMiddleware:
    """Pure ASGI middleware for correlation IDs, duration, and completion logs."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        incoming = _header(scope, b"x-request-id")
        request_id = incoming if valid_request_id(incoming) else uuid4().hex
        request_token = request_id_var.set(request_id)
        kind_token = principal_kind_var.set("-")
        principal_token = principal_id_var.set("-")
        tenant_token = tenant_id_var.set("-")
        started = time.perf_counter()
        status_code = 500

        async def send_with_context(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                headers = list(message.get("headers", []))
                _replace_header(headers, b"x-request-id", request_id.encode("ascii"))
                duration_ms = (time.perf_counter() - started) * 1000
                _replace_header(
                    headers,
                    b"server-timing",
                    f"app;dur={duration_ms:.2f}".encode("ascii"),
                )
                rate_limit = scope.get("state", {}).get("rate_limit")
                if isinstance(rate_limit, dict):
                    for name, key in (
                        (b"x-ratelimit-limit", "limit"),
                        (b"x-ratelimit-remaining", "remaining"),
                        (b"x-ratelimit-reset", "reset"),
                    ):
                        value = rate_limit.get(key)
                        if isinstance(value, int):
                            _replace_header(headers, name, str(value).encode("ascii"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "request_completed",
                extra={
                    "http_method": scope.get("method", "-"),
                    # Route templates avoid leaking identifiers and metric-cardinality
                    # explosions from raw paths. Unmatched paths are deliberately folded.
                    "http_path": _route_template(scope),
                    "http_status": status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            tenant_id_var.reset(tenant_token)
            principal_id_var.reset(principal_token)
            principal_kind_var.reset(kind_token)
            request_id_var.reset(request_token)


def _header(scope: dict[str, Any], name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            try:
                return value.decode("ascii")
            except UnicodeDecodeError:
                return None
    return None


def _replace_header(headers: list[tuple[bytes, bytes]], name: bytes, value: bytes) -> None:
    headers[:] = [(key, item) for key, item in headers if key.lower() != name]
    headers.append((name, value))


def _route_template(scope: dict[str, Any]) -> str:
    route = scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) and template else "/__unmatched__"
