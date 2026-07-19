"""Distributed per-principal API rate limiting backed by Dragonfly/Redis."""

from __future__ import annotations

import hashlib
import logging
import math
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import HTTPException, Request, status

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


async def enforce_principal_rate_limit(request: Request, principal: AuthUser) -> None:
    """Enforce one bounded sliding-window limit after principal authentication."""
    if not getattr(settings, "RATE_LIMIT_ENABLED", True):
        return

    redis: Any | None = getattr(request.app.state, "redis", None)
    if redis is None:
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="rate limiter unavailable",
                headers={"Retry-After": "5"},
            )
        return

    bucket, limit = _request_limit(request)
    actor_digest = hashlib.sha256(
        f"{principal.kind.value}:{principal.user_id}".encode()
    ).hexdigest()[:32]
    key = f"forjd:rate-limit:{actor_digest}:{bucket}"
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


def _request_limit(request: Request) -> tuple[str, int]:
    method = request.method.upper()
    path = request.url.path
    if method == "POST" and path.startswith(("/api/v1/ingest", "/api/v1/siem/signals")):
        return "ingest", max(1, int(getattr(settings, "INGEST_RATE_LIMIT_RPM", 120)))
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return "write", max(1, int(getattr(settings, "WRITE_RATE_LIMIT_RPM", 300)))
    return "read", max(1, int(getattr(settings, "READ_RATE_LIMIT_RPM", 1_200)))
