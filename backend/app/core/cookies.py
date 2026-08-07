"""Secure cookie defaults — FORJD does not set session cookies.

Auth is header-only (``Authorization`` / ``X-API-Key``). Analytics vendors may
set their own cookies; FORJD must not introduce cookie write authority for
``/api/v1``. If a non-auth cookie is ever required (consent/prefs), build it
with ``build_set_cookie`` so Secure / HttpOnly / SameSite cannot be omitted
insecurely.

ADR: docs/adr/0016-secure-defaults-cookies-headers-api.md
"""

from __future__ import annotations

from typing import Literal

from app.core.config import settings

SameSite = Literal["Strict", "Lax", "None"]

# --- Defaults for any future non-auth cookie ---
DEFAULT_PATH = "/"
DEFAULT_SAMESITE: SameSite = "Lax"
DEFAULT_HTTPONLY = True


# --- Set-Cookie builder (fail closed) ---
def build_set_cookie(
    name: str,
    value: str,
    *,
    max_age: int | None = None,
    path: str = DEFAULT_PATH,
    domain: str | None = None,
    secure: bool | None = None,
    httponly: bool = DEFAULT_HTTPONLY,
    samesite: SameSite = DEFAULT_SAMESITE,
) -> str:
    """Return a ``Set-Cookie`` header value with secure defaults.

    ``secure`` defaults to True in production. ``SameSite=None`` requires Secure.
    """
    if not name or any(ch in name for ch in ("\r", "\n", ";", "=", " ", "\t")):
        raise ValueError("invalid cookie name")
    if any(ch in value for ch in ("\r", "\n", ";")):
        raise ValueError("invalid cookie value")
    if path and any(ch in path for ch in ("\r", "\n", ";")):
        raise ValueError("invalid cookie path")

    use_secure = bool(settings.is_production) if secure is None else bool(secure)
    if samesite == "None" and not use_secure:
        raise ValueError("SameSite=None requires Secure")
    if settings.is_production and not use_secure:
        raise ValueError("Secure is required for cookies in production")

    parts = [f"{name}={value}", f"Path={path or DEFAULT_PATH}", f"SameSite={samesite}"]
    if use_secure:
        parts.append("Secure")
    if httponly:
        parts.append("HttpOnly")
    if max_age is not None:
        parts.append(f"Max-Age={max(0, int(max_age))}")
    if domain:
        if any(ch in domain for ch in ("\r", "\n", ";")):
            raise ValueError("invalid cookie domain")
        parts.append(f"Domain={domain}")
    return "; ".join(parts)
