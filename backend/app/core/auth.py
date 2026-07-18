"""Supabase Auth + tenant-scoped service principals for FastAPI.

Principal kinds
---------------
* **user** — Enterprise human via Supabase Auth access token. Tenant access
  comes from `tenant_members` (multi-tenant membership).
* **service** — Machine / subprocessor (partner SaaS backend) bound to **one**
  tenant. Authenticated by:
  1. Opaque token `fjsvc_<prefix>_<secret>` (hashed in `service_accounts`), or
  2. Supabase JWT with `app_metadata.forjd.principal_type = "service"` that
     matches an active `service_accounts.auth_user_id` row.

Partner apps keep their own end-user auth. FORJD never accepts those end-user
tokens — only the subprocessor's tenant-scoped service principal.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
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

# Opaque service token: fjsvc_<8-char-prefix>_<secret>
SERVICE_TOKEN_PREFIX = "fjsvc_"
SERVICE_PREFIX_LEN = 8


class PrincipalKind(StrEnum):
    USER = "user"
    SERVICE = "service"


# --- Verified caller (human or service) ---
@dataclass(frozen=True, slots=True)
class AuthUser:
    """Verified principal from a Bearer credential.

    For users, `user_id` is the Supabase `sub`. For services, `user_id` is the
    `service_accounts.id` (stable actor id for audit / submitted_by).
    """

    user_id: str
    email: str | None
    role: str
    raw_claims: dict[str, Any]
    kind: PrincipalKind = PrincipalKind.USER
    # Bound tenant for SERVICE principals (hard isolation). Users resolve via membership.
    tenant_id: str | None = None
    subprocessor: str | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_service(self) -> bool:
        return self.kind == PrincipalKind.SERVICE

    @property
    def is_user(self) -> bool:
        return self.kind == PrincipalKind.USER

    @property
    def actor_id(self) -> str:
        """Stable audit / telemetry actor string (never plaintext / keys)."""
        if self.is_service:
            return f"svc:{self.user_id}"
        return self.user_id


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
        _jwks_client = PyJWKClient(url, cache_keys=True, lifespan=_JWKS_TTL_SECONDS)
        _jwks_fetched_at = now
    return _jwks_client


def hash_service_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def looks_like_service_token(token: str) -> bool:
    if not token.startswith(SERVICE_TOKEN_PREFIX):
        return False
    rest = token[len(SERVICE_TOKEN_PREFIX) :]
    parts = rest.split("_", 1)
    return len(parts) == 2 and len(parts[0]) == SERVICE_PREFIX_LEN and bool(parts[1])


def service_token_prefix(token: str) -> str | None:
    if not looks_like_service_token(token):
        return None
    rest = token[len(SERVICE_TOKEN_PREFIX) :]
    return rest.split("_", 1)[0]


# --- Claim helpers (Supabase app_metadata.forjd) ---
def _forjd_metadata(claims: dict[str, Any]) -> dict[str, Any] | None:
    """Extract FORJD principal block from JWT claims (never trust alone for authz)."""
    for container_key in ("app_metadata", "user_metadata", "forjd"):
        if container_key == "forjd":
            block = claims.get("forjd")
        else:
            meta = claims.get(container_key)
            if not isinstance(meta, dict):
                continue
            block = meta.get("forjd")
        if isinstance(block, dict) and block.get("principal_type") == "service":
            return block
    return None


# --- JWT verification (user or service claim shape) ---
def verify_supabase_jwt(token: str) -> AuthUser:
    """Validate a Supabase access token. Service claim shape is provisional until DB check."""
    options = {
        "require": ["exp", "sub", "role"],
        "verify_aud": bool(settings.SUPABASE_JWT_AUDIENCE),
    }
    audience = settings.SUPABASE_JWT_AUDIENCE or None
    issuer = None
    if settings.SUPABASE_URL.strip():
        issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"

    last_err: Exception | None = None
    claims: dict[str, Any] | None = None

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
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.debug("JWKS JWT verify failed, trying HS256 fallback: %s", exc)

    if claims is None:
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
            except Exception as exc:  # noqa: BLE001
                last_err = exc

    if claims is None:
        detail = "invalid or expired token"
        if settings.DEBUG and last_err is not None:
            detail = f"invalid or expired token ({last_err})"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    return _principal_from_claims(claims)


def _principal_from_claims(claims: dict[str, Any]) -> AuthUser:
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing sub")

    forjd = _forjd_metadata(claims)
    if forjd is not None:
        # Provisional service shape — get_current_user binds to service_accounts.
        tenant = forjd.get("tenant_id")
        scopes_raw = forjd.get("scopes") or []
        if isinstance(scopes_raw, list):
            scopes = frozenset(str(s) for s in scopes_raw)
        else:
            scopes = frozenset()
        return AuthUser(
            user_id=str(sub),
            email=(claims.get("email") if isinstance(claims.get("email"), str) else None),
            role=str(claims.get("role") or "authenticated"),
            raw_claims=claims,
            kind=PrincipalKind.SERVICE,
            tenant_id=str(tenant) if tenant else None,
            subprocessor=str(forjd.get("subprocessor") or "") or None,
            scopes=scopes,
        )

    # Reject Supabase service_role JWT on app routes (too privileged / wrong model).
    role = str(claims.get("role") or "authenticated")
    if role == "service_role":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="service_role JWT is not accepted; use a tenant-scoped service account",
        )

    return AuthUser(
        user_id=str(sub),
        email=(claims.get("email") if isinstance(claims.get("email"), str) else None),
        role=role,
        raw_claims=claims,
        kind=PrincipalKind.USER,
    )


# --- Opaque service token → DB principal ---
async def _authenticate_opaque_service(pool: Any, token: str) -> AuthUser:
    from app.services import service_accounts as svc_accounts

    prefix = service_token_prefix(token)
    if prefix is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid service token",
        )
    row = await svc_accounts.authenticate_opaque(pool, prefix=prefix, token=token)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid service token",
        )
    return _auth_user_from_service_row(row, raw_claims={"auth": "opaque_service_token"})


def _auth_user_from_service_row(row: dict[str, Any], *, raw_claims: dict[str, Any]) -> AuthUser:
    scopes = row.get("scopes") or []
    return AuthUser(
        user_id=str(row["id"]),
        email=None,
        role="service",
        raw_claims=raw_claims,
        kind=PrincipalKind.SERVICE,
        tenant_id=str(row["tenant_id"]),
        subprocessor=(str(row["subprocessor"]) if row.get("subprocessor") else None),
        scopes=frozenset(str(s) for s in scopes),
    )


async def _bind_jwt_service_principal(pool: Any, provisional: AuthUser) -> AuthUser:
    """Map a service-shaped JWT to the active service_accounts row (DB is source of truth)."""
    from app.services import service_accounts as svc_accounts

    # provisional.user_id is Supabase auth user sub until rebound to service_accounts.id
    row = await svc_accounts.authenticate_auth_user(pool, auth_user_id=provisional.user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="service account not registered or revoked",
        )
    bound = _auth_user_from_service_row(
        row,
        raw_claims={**provisional.raw_claims, "auth": "supabase_service_jwt"},
    )
    # Hard isolation: JWT claim tenant (if present) must match registry.
    if provisional.tenant_id and provisional.tenant_id != bound.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="service token tenant mismatch",
        )
    return bound


# --- FastAPI dependencies ---
async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    """Require a valid user JWT or tenant-scoped service credential."""
    if creds is None or creds.scheme.lower() != "bearer":
        if settings.SUPABASE_AUTH_REQUIRED or auth_configured():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth not configured")

    token = creds.credentials
    pool = pool_from_request(request)

    # Opaque M2M token (subprocessors) — does not need JWKS.
    if looks_like_service_token(token):
        if pool is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database unavailable",
            )
        return await _authenticate_opaque_service(pool, token)

    if not auth_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth is not configured (set SUPABASE_URL or SUPABASE_JWT_SECRET)",
        )

    principal = verify_supabase_jwt(token)
    if principal.is_service:
        if pool is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database unavailable",
            )
        return await _bind_jwt_service_principal(pool, principal)
    return principal


async def get_optional_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser | None:
    if creds is None or creds.scheme.lower() != "bearer":
        return None
    try:
        return await get_current_user(request, creds)
    except HTTPException:
        return None


def require_user_principal(user: AuthUser) -> AuthUser:
    """Reject service tokens on human-only routes (tenant create, mint keys, …)."""
    if user.is_service:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="enterprise user JWT required (service tokens cannot perform this action)",
        )
    return user


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
