"""Distributed API rate limiting backed by Dragonfly/Redis."""

from __future__ import annotations

import hashlib
import logging
import math
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

if TYPE_CHECKING:
    from app.core.auth import AuthUser

logger = logging.getLogger("forjd.rate_limit")

_WINDOW_MS = 60_000
_SLIDING_WINDOW = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[1] - ARGV[3])
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[2]) then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  local retry = tonumber(ARGV[3])
  if oldest[2] then
    retry = math.max(1, tonumber(ARGV[3]) - (ARGV[1] - tonumber(oldest[2])))
  end
  return {0, count, retry}
end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('PEXPIRE', KEYS[1], ARGV[3])
local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
local reset = tonumber(ARGV[3])
if oldest[2] then
  reset = math.max(1, tonumber(ARGV[3]) - (ARGV[1] - tonumber(oldest[2])))
end
return {1, count + 1, reset}
"""

# --- Anonymous public routes (IP sliding window) ---
_PUBLIC_RATE_LIMIT_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/status/pages/slug/"),
    ("GET", "/capabilities"),
    ("GET", "/addons"),
    ("POST", "/honeypots/hit"),
)


async def enforce_principal_rate_limit(request: Request, principal: AuthUser) -> None:
    """Enforce one bounded sliding-window limit after principal authentication."""
    if not getattr(settings, "RATE_LIMIT_ENABLED", True):
        return

    bucket, limit = _request_limit(request)
    actor_digest = hashlib.sha256(
        f"{principal.kind.value}:{principal.user_id}".encode()
    ).hexdigest()[:32]
    key = f"forjd:rate-limit:{actor_digest}:{bucket}"
    await _enforce_sliding_window(request, key=key, limit=limit)


async def enforce_ip_rate_limit(request: Request, *, bucket: str, limit: int) -> None:
    """Enforce a sliding-window limit keyed by hashed client IP + bucket."""
    if not getattr(settings, "RATE_LIMIT_ENABLED", True):
        return

    bound = max(1, int(limit))
    ip_digest = hashlib.sha256(_client_ip(request).encode()).hexdigest()[:32]
    key = f"forjd:rate-limit:ip:{ip_digest}:{bucket}"
    await _enforce_sliding_window(request, key=key, limit=bound)


# --- Shared Redis sliding window ---
async def _enforce_sliding_window(request: Request, *, key: str, limit: int) -> None:
    redis: Any | None = getattr(request.app.state, "redis", None)
    if redis is None:
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="rate limiter unavailable",
                headers={"Retry-After": "5"},
            )
        return

    now_ms = int(time.time() * 1000)
    member = f"{now_ms}:{uuid4().hex}"
    try:
        raw = await redis.eval(
            _SLIDING_WINDOW,
            1,
            key,
            now_ms,
            limit,
            _WINDOW_MS,
            member,
        )
        allowed, count, retry_ms = (int(raw[0]), int(raw[1]), int(raw[2]))
    except Exception as exc:  # noqa: BLE001
        if settings.is_production:
            logger.error("rate limiter failed closed: %s", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="rate limiter unavailable",
                headers={"Retry-After": "5"},
            ) from exc
        logger.warning("rate limiter unavailable in development: %s", type(exc).__name__)
        return

    request.state.rate_limit = {
        "limit": limit,
        "remaining": max(0, limit - count),
        "reset": max(0, math.ceil(retry_ms / 1000)),
    }
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": str(max(1, math.ceil(retry_ms / 1000)))},
        )


def _client_ip(request: Request) -> str:
    """First X-Forwarded-For hop, else request.client.host (never log raw)."""
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    return str(host) if host else "unknown"


def _request_limit(request: Request) -> tuple[str, int]:
    method = request.method.upper()
    path = request.url.path
    if method == "POST" and path.startswith(("/api/v1/ingest", "/api/v1/siem/signals")):
        return "ingest", max(1, int(getattr(settings, "INGEST_RATE_LIMIT_RPM", 120)))
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return "write", max(1, int(getattr(settings, "WRITE_RATE_LIMIT_RPM", 300)))
    return "read", max(1, int(getattr(settings, "READ_RATE_LIMIT_RPM", 1_200)))


def _matches_public_rate_limit(request: Request) -> bool:
    method = request.method.upper()
    path = request.url.path.rstrip("/") or "/"
    prefix = settings.API_V1_STR.rstrip("/")
    for route_method, suffix in _PUBLIC_RATE_LIMIT_ROUTES:
        if method != route_method:
            continue
        target = f"{prefix}{suffix}".rstrip("/")
        if suffix.endswith("/"):
            # Prefix match for slug and similar path params.
            if path.startswith(f"{prefix}{suffix}") or path.startswith(target + "/"):
                return True
            continue
        if path == target:
            return True
    return False


# --- Middleware for anonymous public endpoints ---
class PublicRateLimitMiddleware(BaseHTTPMiddleware):
    """IP rate limit on selected unauthenticated public API routes."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not getattr(settings, "RATE_LIMIT_ENABLED", True):
            return await call_next(request)
        if not _matches_public_rate_limit(request):
            return await call_next(request)
        try:
            await enforce_ip_rate_limit(
                request,
                bucket="public",
                limit=int(getattr(settings, "PUBLIC_RATE_LIMIT_RPM", 120)),
            )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=dict(exc.headers or {}),
            )
        return await call_next(request)
