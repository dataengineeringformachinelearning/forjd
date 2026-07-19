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
* **erase_tombstone** — A deleted opaque service credential matched only by a
  completed same-tenant erase receipt, on the exact erase-retry route. It has
  no general service scopes.

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
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings
from app.core.rate_limit import enforce_principal_rate_limit
from app.core.request_context import bind_principal_context

logger = logging.getLogger("forjd.auth")

# --- Module state (JWKS cache) ---
_bearer = HTTPBearer(auto_error=False)
_jwks_client: PyJWKClient | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SECONDS = 3600.0

# Opaque service token: fjsvc_<8-char-prefix>_<secret>
SERVICE_TOKEN_PREFIX = "fjsvc_"
SERVICE_PREFIX_LEN = 8

# Rate-limited auth failure logs (never log full tokens).
_AUTH_FAIL_LOG: dict[str, float] = {}
_AUTH_FAIL_LOG_INTERVAL = 60.0


def _log_auth_failure(*, kind: str, reason: str, token_prefix: str = "") -> None:
    """Structured 401 observability without leaking secrets."""
    key = f"{kind}:{reason}:{token_prefix[:8]}"
    now = time.monotonic()
    last = _AUTH_FAIL_LOG.get(key, 0.0)
    if now - last < _AUTH_FAIL_LOG_INTERVAL:
        return
    _AUTH_FAIL_LOG[key] = now
    logger.warning(
        "auth_failed kind=%s reason=%s token_prefix=%s",
        kind,
        reason,
        token_prefix[:8] or "-",
    )


class PrincipalKind(StrEnum):
    USER = "user"
    SERVICE = "service"
    # A deleted opaque credential may prove only that its completed erase
    # receipt belongs to the same tenant. It is never a general service actor.
    ERASE_TOMBSTONE = "erase_tombstone"


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
    # Populated only after a live opaque token has passed the service_accounts
    # hash comparison. The raw token is never attached to the principal.
    opaque_token_prefix: str | None = None
    opaque_token_hash: str | None = field(default=None, repr=False)

    @property
    def is_service(self) -> bool:
        return self.kind == PrincipalKind.SERVICE

    @property
    def is_user(self) -> bool:
        return self.kind == PrincipalKind.USER

    @property
    def is_erase_tombstone(self) -> bool:
        return self.kind == PrincipalKind.ERASE_TOMBSTONE

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


# --- Claim helpers (Supabase app_metadata.forjd only — never user_metadata) ---
def _forjd_metadata(claims: dict[str, Any]) -> dict[str, Any] | None:
    """Extract FORJD service principal block from JWT claims.

    Only ``app_metadata.forjd`` is trusted (admin-controlled). ``user_metadata``
    is user-writable in Supabase and must never grant service shape.
    Binding still requires a matching ``service_accounts`` row at request time.
    """
    meta = claims.get("app_metadata")
    if isinstance(meta, dict):
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

    # Never take ``alg`` from the unverified header (algorithm confusion).
    _JWKS_ALGORITHMS = ["ES256", "RS256"]

    jwks = _get_jwks_client()
    if jwks is not None:
        try:
            key = jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=_JWKS_ALGORITHMS,
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

    # Reject Supabase service_role before any forjd claim shaping (fail closed).
    role = str(claims.get("role") or "authenticated")
    if role == "service_role":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="service_role JWT is not accepted; use a tenant-scoped service account",
        )

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
            role=role,
            raw_claims=claims,
            kind=PrincipalKind.SERVICE,
            tenant_id=str(tenant) if tenant else None,
            subprocessor=str(forjd.get("subprocessor") or "") or None,
            scopes=scopes,
        )

    return AuthUser(
        user_id=str(sub),
        email=(claims.get("email") if isinstance(claims.get("email"), str) else None),
        role=role,
        raw_claims=claims,
        kind=PrincipalKind.USER,
    )


# --- Opaque service token → DB principal ---
def _erase_retry_tenant_id(request: Request) -> UUID | None:
    """Return the tenant only for the exact completed-erase retry route.

    Route-template matching is intentional: a tombstoned credential must not
    become valid merely because an unrelated URL happens to contain
    ``/tenants/`` and ``/erase``.
    """
    if request.method.upper() != "POST":
        return None
    route = request.scope.get("route")
    expected = f"{settings.API_V1_STR.rstrip('/')}/tenants/{{tenant_id}}/erase"
    if getattr(route, "path", None) != expected:
        return None
    raw_tenant_id = request.path_params.get("tenant_id")
    try:
        return UUID(str(raw_tenant_id))
    except (TypeError, ValueError):
        return None


async def _authenticate_opaque_service(
    pool: Any,
    token: str,
    *,
    request: Request | None = None,
) -> AuthUser:
    from app.services import service_accounts as svc_accounts

    prefix = service_token_prefix(token)
    if prefix is None:
        _log_auth_failure(kind="opaque", reason="bad_shape")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid service token",
        )
    retry_tenant_id = _erase_retry_tenant_id(request) if request is not None else None
    row = await svc_accounts.authenticate_opaque(pool, prefix=prefix, token=token)
    if row is not None:
        return _auth_user_from_service_row(
            row,
            raw_claims={"auth": "opaque_service_token"},
            opaque_token_prefix=prefix if retry_tenant_id is not None else None,
            opaque_token_hash=(hash_service_token(token) if retry_tenant_id is not None else None),
        )

    # Lost-response recovery after tenant erase. This lookup is unreachable for
    # every other route/method and accepts only a completed receipt for the same
    # tenant. The tombstone principal has no reusable service scopes.
    if retry_tenant_id is not None:
        tombstone = await svc_accounts.authenticate_erased_opaque(
            pool,
            tenant_id=retry_tenant_id,
            prefix=prefix,
            token=token,
        )
        if tombstone is not None:
            return _auth_user_from_erase_tombstone(tombstone)

    _log_auth_failure(kind="opaque", reason="reject", token_prefix=prefix)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid service token",
    )


def _auth_user_from_service_row(
    row: dict[str, Any],
    *,
    raw_claims: dict[str, Any],
    opaque_token_prefix: str | None = None,
    opaque_token_hash: str | None = None,
) -> AuthUser:
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
        opaque_token_prefix=opaque_token_prefix,
        opaque_token_hash=opaque_token_hash,
    )


def _auth_user_from_erase_tombstone(row: dict[str, Any]) -> AuthUser:
    """Build a non-service principal valid only for receipt replay."""
    prefix = str(row["erased_credential_prefix"])
    return AuthUser(
        user_id=f"erased:{prefix}",
        email=None,
        role="erase_tombstone",
        raw_claims={"auth": "erased_opaque_tombstone"},
        kind=PrincipalKind.ERASE_TOMBSTONE,
        tenant_id=str(row["tenant_id"]),
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
        _log_auth_failure(kind="bearer", reason="missing")
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
        principal = await _authenticate_opaque_service(pool, token, request=request)
        return await _finalize_principal(request, principal)

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
        principal = await _bind_jwt_service_principal(pool, principal)
    return await _finalize_principal(request, principal)


async def _finalize_principal(request: Request, principal: AuthUser) -> AuthUser:
    _bind_log_context(principal)
    await enforce_principal_rate_limit(request, principal)
    return principal


def _bind_log_context(principal: AuthUser) -> None:
    bind_principal_context(
        principal_kind=principal.kind.value,
        principal_id=principal.user_id,
        tenant_id=principal.tenant_id,
    )


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
    if not user.is_user:
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
