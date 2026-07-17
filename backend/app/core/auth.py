"""Supabase Auth JWT verification for FastAPI.

Supports:
  • JWKS (ES256 / RS256) from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`
  • Legacy HS256 with `SUPABASE_JWT_SECRET` (Project Settings → API → JWT Secret)

When `SUPABASE_AUTH_REQUIRED=true`, protected routes reject missing/invalid tokens.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings

logger = logging.getLogger("forjd.auth")

# --- Module state (JWKS cache) ---
_bearer = HTTPBearer(auto_error=False)
_jwks_client: PyJWKClient | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SECONDS = 3600.0


@dataclass(frozen=True, slots=True)
class AuthUser:
    """Verified Supabase user from a JWT access token."""

    user_id: str
    email: str | None
    role: str
    raw_claims: dict[str, Any]


# --- Config / JWKS client ---
def auth_configured() -> bool:
    return bool(settings.SUPABASE_URL.strip() or settings.SUPABASE_JWT_SECRET.strip())


def _jwks_url() -> str | None:
    base = settings.SUPABASE_URL.rstrip("/")
    if not base:
        return None
    return f"{base}/auth/v1/.well-known/jwks.json"


def _get_jwks_client() -> PyJWKClient | None:
    global _jwks_client, _jwks_fetched_at
    url = _jwks_url()
    if not url:
        return None
    now = time.monotonic()
    if _jwks_client is None or (now - _jwks_fetched_at) > _JWKS_TTL_SECONDS:
        # PyJWKClient fetches on demand; recreate periodically for key rotation.
        _jwks_client = PyJWKClient(url, cache_keys=True, lifespan=_JWKS_TTL_SECONDS)
        _jwks_fetched_at = now
    return _jwks_client


# --- JWT verification ---
def verify_supabase_jwt(token: str) -> AuthUser:
    """Validate a Supabase access token and return the subject user."""
    options = {
        "require": ["exp", "sub", "role"],
        "verify_aud": bool(settings.SUPABASE_JWT_AUDIENCE),
    }
    audience = settings.SUPABASE_JWT_AUDIENCE or None
    issuer = None
    if settings.SUPABASE_URL.strip():
        issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"

    last_err: Exception | None = None

    # Prefer asymmetric JWKS when URL is set.
    jwks = _get_jwks_client()
    if jwks is not None:
        try:
            header = jwt.get_unverified_header(token)
            key = jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=[header.get("alg", "ES256")],
                audience=audience,
                issuer=issuer,
                options=options,
            )
            return _user_from_claims(claims)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.debug("JWKS JWT verify failed, trying HS256 fallback: %s", exc)

    # Fallback: legacy HS256 JWT secret from Supabase dashboard.
    secret = settings.SUPABASE_JWT_SECRET.strip()
    if secret:
        try:
            claims = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=audience,
                issuer=issuer,
                options=options,
            )
            return _user_from_claims(claims)
        except Exception as exc:  # noqa: BLE001
            last_err = exc

    detail = "invalid or expired token"
    if settings.DEBUG and last_err is not None:
        detail = f"invalid or expired token ({last_err})"
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _user_from_claims(claims: dict[str, Any]) -> AuthUser:
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing sub")
    return AuthUser(
        user_id=str(sub),
        email=(claims.get("email") if isinstance(claims.get("email"), str) else None),
        role=str(claims.get("role") or "authenticated"),
        raw_claims=claims,
    )


# --- FastAPI dependencies ---
async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    """Require a valid Supabase JWT (unless auth is not configured and not required)."""
    if creds is None or creds.scheme.lower() != "bearer":
        if settings.SUPABASE_AUTH_REQUIRED or auth_configured():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth not configured")

    if not auth_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth is not configured (set SUPABASE_URL or SUPABASE_JWT_SECRET)",
        )
    return verify_supabase_jwt(creds.credentials)


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser | None:
    if creds is None or creds.scheme.lower() != "bearer":
        return None
    if not auth_configured():
        return None
    try:
        return verify_supabase_jwt(creds.credentials)
    except HTTPException:
        return None


def pool_from_request(request: Request):
    """Postgres pool attached in app lifespan (may be None if soft-connect failed)."""
    return getattr(request.app.state, "db_pool", None)


# --- Startup ---
async def warm_jwks() -> None:
    """Best-effort JWKS prefetch at startup."""
    url = _jwks_url()
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code < 400:
                _get_jwks_client()
                logger.info("supabase JWKS reachable")
    except Exception:  # noqa: BLE001
        logger.warning("supabase JWKS warm failed", exc_info=True)
