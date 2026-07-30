"""Security middleware — headers, HTTPS redirect, optional API key gate.

ADR: docs/adr/0013-client-side-attack-hardening.md,
docs/adr/0016-secure-defaults-cookies-headers-api.md
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.auth import _log_auth_failure
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


# API JSON stays locked down. HTML shells (/ , /docs, /redoc) use self-hosted
# suite CSS + vendored Swagger/ReDoc under /static/vendor/ (no jsDelivr).
# Landing retains 'unsafe-inline' scripts for gtag/Clarity boot snippets only.
# CSRF is not token-based here: mutating routes require Authorization / X-API-Key
# (header credentials are not auto-attached by browsers the way cookies are).
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
_HTML_SHELL_CSP = (
    "default-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "script-src 'self' 'unsafe-inline' "
    "https://www.googletagmanager.com https://*.googletagmanager.com "
    "https://www.clarity.ms https://*.clarity.ms; "
    "style-src 'self'; "
    "img-src 'self' data: "
    "https://c.clarity.ms https://*.clarity.ms "
    "https://*.google-analytics.com https://*.googletagmanager.com; "
    "font-src 'self' data:; "
    "connect-src 'self' "
    "https://*.google-analytics.com https://*.analytics.google.com "
    "https://*.googletagmanager.com https://*.clarity.ms https://*.bing.com"
)
_HTML_SHELL_PATHS = frozenset({"/", "/docs", "/redoc"})
_REDOC_NONCE_STATE_KEY = "redoc_csp_nonce"
# The vendored ReDoc bundle injects perfect-scrollbar's static stylesheet before
# Redoc.init can apply its nonce. Admit that exact, immutable stylesheet without
# weakening the rest of the ReDoc policy to unsafe-inline.
_REDOC_SCROLLBAR_STYLE_HASH = "'sha256-QMIg+bpjm3JdElJ388KYke01izlUW0UoNOeKjpMxdgc='"
# styled-components creates an empty bootstrap style before it applies the
# configured nonce. This hash admits only that empty block.
_REDOC_EMPTY_STYLE_HASH = "'sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU='"


def _csp_for_path(path: str, *, redoc_nonce: str | None = None) -> str:
    if path in _HTML_SHELL_PATHS:
        if path == "/redoc" and redoc_nonce:
            redoc_csp = _HTML_SHELL_CSP.replace(
                "style-src 'self'",
                "style-src 'self' "
                f"'nonce-{redoc_nonce}' "
                f"{_REDOC_SCROLLBAR_STYLE_HASH} "
                f"{_REDOC_EMPTY_STYLE_HASH}",
            )
            redoc_csp = redoc_csp.replace(
                "img-src 'self' data:",
                "img-src 'self' data: https://cdn.redoc.ly",
            )
            return f"{redoc_csp}; worker-src 'self' blob:"
        return _HTML_SHELL_CSP
    return _API_CSP


# --- Production HTTP → HTTPS (edge X-Forwarded-Proto) ---
class HttpsRedirectMiddleware(BaseHTTPMiddleware):
    """308 to HTTPS when production sees cleartext via the edge proxy."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if settings.is_production:
            proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
            if proto == "http":
                https_url = request.url.replace(scheme="https")
                return RedirectResponse(url=str(https_url), status_code=308)
        return await call_next(request)


# --- Response security headers ---
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        redoc_nonce = None
        if request.url.path == "/redoc":
            redoc_nonce = secrets.token_urlsafe(24)
            setattr(request.state, _REDOC_NONCE_STATE_KEY, redoc_nonce)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=(), "
            "bluetooth=(), interest-cohort=(), browsing-topics=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            _csp_for_path(request.url.path, redoc_nonce=redoc_nonce),
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        response.headers.setdefault("Cache-Control", "no-store")
        # HSTS whenever Settings treats the process as production-like (prod/staging/Fly).
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
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

        # Dual gate when configured: X-API-Key (or Bearer equal to API_KEY) is
        # always required for mutating /api/v1 routes. Do not skip on JWT/fjsvc_
        # shape — unauthenticated mutating routes (e.g. honeypot hits) would
        # otherwise bypass the shared key with a forged Bearer token.
        provided = (request.headers.get("x-api-key") or "").strip()
        if not provided:
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
                # Only accept Bearer when it *is* the shared API key. Route auth
                # still validates Supabase JWTs / fjsvc_ principals separately.
                if token and hmac.compare_digest(token, expected):
                    provided = token

        if not provided or not hmac.compare_digest(provided, expected):
            _log_auth_failure(kind="api_key", reason="reject")
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or missing API key"},
            )
        return await call_next(request)
