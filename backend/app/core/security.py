"""Security middleware — headers and optional API key gate for mutating routes."""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

# --- Public path helpers (no API key) ---
_PUBLIC_PREFIXES = (
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _is_public(path: str) -> bool:
    return path == "/" or any(path == p or path.startswith(p + "/") for p in _PUBLIC_PREFIXES)


def _is_mutating(method: str) -> bool:
    return method.upper() in {"POST", "PUT", "PATCH", "DELETE"}


# API responses are JSON/docs — strict CSP; browsers that render docs stay locked down.
# CSRF is not token-based here: mutating routes require Authorization / X-API-Key
# (header credentials are not auto-attached by browsers the way cookies are).
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


# --- Response security headers ---
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )
        response.headers.setdefault("Content-Security-Policy", _API_CSP)
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        response.headers.setdefault("Cache-Control", "no-store")
        # HSTS only when clearly behind TLS / production.
        if settings.ENVIRONMENT.lower() in {"production", "prod"}:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


# --- Optional shared API key (does not consume Supabase Bearer JWTs) ---
class ApiKeyMiddleware(BaseHTTPMiddleware):
    """When `API_KEY` is set, require it on mutating `/api/*` routes."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        expected = settings.API_KEY.strip()
        if not expected or not _is_mutating(request.method) or _is_public(request.url.path):
            return await call_next(request)

        if not request.url.path.startswith(settings.API_V1_STR):
            return await call_next(request)

        # Prefer X-API-Key. Bearer JWTs, tenant service tokens (fjsvc_…), and the
        # partner provision bootstrap token are left for route auth.
        provided = (request.headers.get("x-api-key") or "").strip()
        auth = request.headers.get("authorization") or ""
        if not provided and auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            provision = (settings.FORJD_PROVISION_TOKEN or "").strip()
            if (
                token.count(".") == 2
                or token.startswith("fjsvc_")
                or (provision and hmac.compare_digest(token, provision))
            ):
                return await call_next(request)
            provided = token

        if not provided or not hmac.compare_digest(provided, expected):
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or missing API key"},
            )
        return await call_next(request)
