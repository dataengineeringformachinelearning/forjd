"""Sanitize user-generated and third-party text before store / log / return.

Plain-text fields never keep HTML markup. Secrets are scrubbed for observability.
Ciphertext envelopes are out of scope — they stay opaque base64 (ADR-0002).

ADR: docs/adr/0014-sanitize-ugc-and-third-party.md,
docs/adr/0017-secrets-and-sensitive-data.md
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any

# --- Patterns ---
_TAG_RE = re.compile(r"<[^>]*>", re.DOTALL)
# Exact key names (normalized: lower, `-` → `_`). Keep in lockstep with scrub.ts.
_SECRET_KEY_EXACT_RE = re.compile(
    r"^(authorization|cookie|set_cookie|x_api_key|x_engine_token|password|secret|"
    r"token|fjsvc_|ciphertext|sealed_payload|private_key|api_key|hibp_api_key|"
    r"access_token|refresh_token|api_token|provision_token|engine_token|"
    r"signing_secret|client_secret|jwt_secret|supabase_jwt_secret|"
    r"dsn|sentry_dsn|rollbar_access_token|hf_token|postgres_dsn|redis_url|"
    r"database_url|webhook_secret|object_storage_secret_access_key)$",
    re.IGNORECASE,
)
# Suffix / segment match — catches nested names like `webhook_signing_secret`.
_SECRET_KEY_SUFFIX_RE = re.compile(
    r"(^|_)(password|secret|token|api_key|private_key|ciphertext|sealed_payload|"
    r"access_token|refresh_token)$",
    re.IGNORECASE,
)
# Values: service tokens, Bearer, JWTs, DB/cache URLs (often embed passwords).
_SECRET_VALUE_RE = re.compile(
    r"\b(fjsvc_[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._\-]+|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b|"
    r"\b(?:postgres(?:ql)?|redis|rediss)://[^\s\"'<>]+",
    re.IGNORECASE,
)

# Back-compat alias used by older call sites / tests.
_SECRET_KEY_RE = _SECRET_KEY_EXACT_RE


def _normalize_secret_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def is_secret_key(key: str) -> bool:
    """True when a dict key should be fully redacted in logs/trackers."""
    normalized = _normalize_secret_key(key)
    if not normalized:
        return False
    if _SECRET_KEY_EXACT_RE.fullmatch(normalized):
        return True
    return bool(_SECRET_KEY_SUFFIX_RE.search(normalized))


def _strip_controls(text: str, *, allow_newlines: bool) -> str:
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if ch == "\x00":
            continue
        if ch in "\t\n\r":
            if allow_newlines:
                out.append(ch if ch != "\r" else "\n")
            elif ch == "\t":
                out.append(" ")
            continue
        # Drop other C0 / DEL / C1 controls.
        if code < 32 or code == 127 or 0x80 <= code <= 0x9F:
            continue
        out.append(ch)
    return "".join(out)


# --- Plain UGC text ---
def sanitize_text(
    value: str | None,
    *,
    max_length: int | None = None,
    allow_newlines: bool = False,
) -> str:
    """Normalize and strip markup/controls from a plain-text field."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    text = html.unescape(text)
    text = _TAG_RE.sub("", text)
    text = _strip_controls(text, allow_newlines=allow_newlines)
    if allow_newlines:
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
    else:
        text = re.sub(r"\s+", " ", text)
    text = text.strip()
    if max_length is not None and max_length >= 0 and len(text) > max_length:
        text = text[:max_length].rstrip()
    return text


def sanitize_label(value: str | None, *, max_length: int = 255) -> str:
    """Titles / names — single-line plain text."""
    return sanitize_text(value, max_length=max_length, allow_newlines=False)


def sanitize_body(value: str | None, *, max_length: int = 8192) -> str:
    """Longer UGC (incident body, descriptions) — newlines ok, no HTML."""
    return sanitize_text(value, max_length=max_length, allow_newlines=True)


# --- Third-party / untrusted JSON ---
def sanitize_external(
    value: Any,
    *,
    depth: int = 0,
    max_depth: int = 8,
    max_str: int = 4096,
    max_list: int = 500,
    max_keys: int = 100,
) -> Any:
    """Recursively sanitize third-party JSON-ish data for store/return."""
    if depth > max_depth:
        return "[Truncated]"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return sanitize_text(value, max_length=max_str, allow_newlines=True)
    if isinstance(value, bytes):
        return sanitize_text(value.decode("utf-8", errors="replace"), max_length=max_str)
    if isinstance(value, list):
        return [
            sanitize_external(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_str=max_str,
                max_list=max_list,
                max_keys=max_keys,
            )
            for item in value[:max_list]
        ]
    if isinstance(value, tuple):
        return tuple(
            sanitize_external(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_str=max_str,
                max_list=max_list,
                max_keys=max_keys,
            )
            for item in value[:max_list]
        )
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for index, (raw_key, nested) in enumerate(value.items()):
            if index >= max_keys:
                break
            key = sanitize_label(str(raw_key), max_length=128) or f"key_{index}"
            if is_secret_key(key):
                out[key] = "[Filtered]"
            else:
                out[key] = sanitize_external(
                    nested,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_str=max_str,
                    max_list=max_list,
                    max_keys=max_keys,
                )
        return out
    return sanitize_text(str(value), max_length=max_str)


# --- Observability scrub (secrets / ciphertext) ---
def scrub_secret_string(value: str) -> str:
    return _SECRET_VALUE_RE.sub("[Filtered]", value)


def scrub_for_logs(value: Any, *, depth: int = 0, max_depth: int = 6) -> Any:
    """Deep scrub for logs/Sentry/Rollbar — mirrors frontend scrub.ts."""
    if depth > max_depth:
        return "[Truncated]"
    if isinstance(value, str):
        return scrub_secret_string(value)
    if isinstance(value, list):
        return [scrub_for_logs(item, depth=depth + 1, max_depth=max_depth) for item in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, nested in value.items():
            key_str = str(key)
            if is_secret_key(key_str):
                out[key_str] = "[Filtered]"
            else:
                out[key_str] = scrub_for_logs(nested, depth=depth + 1, max_depth=max_depth)
        return out
    return value
