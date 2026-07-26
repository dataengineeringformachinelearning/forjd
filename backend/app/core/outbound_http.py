"""Defensive outbound HTTP — timeouts, no redirects, byte caps, JSON shapes.

Third-party JSON is sanitized via ``sanitize_external`` (ADR-0014). Errors are
plain strings suitable for soft envelopes (scrub separately when logging —
ADR-0017). Do not use this for inbound partner ingest (see ingest body limit).

ADR: docs/adr/0018-defensive-outbound-http.md
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.sanitize import sanitize_external, sanitize_text

# Align with TAXII / playbook outbound caps.
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_CONNECT_TIMEOUT = 5.0


# --- Structured failure (soft-envelope friendly) ---
class OutboundHttpError(RuntimeError):
    """Outbound HTTP / decode / shape failure without leaking response bodies."""

    def __init__(
        self,
        message: str,
        *,
        kind: str = "error",
        status_code: int | None = None,
    ) -> None:
        self.kind = kind
        self.status_code = status_code
        super().__init__(sanitize_text(message, max_length=256) or "outbound error")


def bounded_timeout(timeout: float, *, connect: float = DEFAULT_CONNECT_TIMEOUT) -> httpx.Timeout:
    """Clamp overall timeout and keep connect bounded."""
    overall = max(1.0, min(float(timeout), 60.0))
    return httpx.Timeout(overall, connect=min(connect, overall))


# --- Body / JSON ---
async def read_bounded_body(
    response: httpx.Response,
    *,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> bytes:
    """Stream response body with a hard byte cap (works with ``client.stream``)."""
    if 300 <= response.status_code < 400:
        raise OutboundHttpError(
            "redirects are not allowed",
            kind="redirect",
            status_code=response.status_code,
        )
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise OutboundHttpError(
                    f"response exceeds {max_bytes} bytes",
                    kind="too_large",
                    status_code=response.status_code,
                )
        except ValueError:
            pass

    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > max_bytes:
            raise OutboundHttpError(
                f"response exceeds {max_bytes} bytes",
                kind="too_large",
                status_code=response.status_code,
            )
        chunks.append(chunk)
    return b"".join(chunks)


def parse_json_bytes(
    raw: bytes,
    *,
    sanitize: bool = True,
    max_str: int = 4096,
    max_list: int = 500,
) -> Any:
    """Decode UTF-8 JSON; optionally run ``sanitize_external``."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OutboundHttpError("response is not utf-8", kind="decode") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OutboundHttpError("response is not valid JSON", kind="json") from exc
    if sanitize:
        return sanitize_external(data, max_str=max_str, max_list=max_list)
    return data


def parse_response_content(
    response: httpx.Response,
    *,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    sanitize: bool = True,
) -> Any:
    """Parse an already-buffered ``response.content`` with a size guard."""
    content = response.content
    if len(content) > max_bytes:
        raise OutboundHttpError(
            f"response exceeds {max_bytes} bytes",
            kind="too_large",
            status_code=response.status_code,
        )
    return parse_json_bytes(content, sanitize=sanitize)


# --- Shape guards ---
def expect_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def expect_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def expect_list_of_dicts(value: Any, *, max_items: int = 500) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value[: max(0, max_items)]:
        if isinstance(item, dict):
            out.append(item)
    return out


# --- Convenience request ---
async def request_json(
    method: str,
    url: str,
    *,
    timeout: float = 15.0,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    sanitize: bool = True,
    accept_statuses: frozenset[int] | None = None,
) -> tuple[int, Any]:
    """GET/POST JSON with no redirects, bounded body, and soft shape defaults.

    Returns ``(status_code, parsed)``. Raises ``OutboundHttpError`` on transport,
    redirect, size, decode, or unexpected HTTP status (unless listed in
    ``accept_statuses``). Allowed 4xx bodies that are not JSON return ``None``.
    """
    allowed = accept_statuses or frozenset()
    async with (
        httpx.AsyncClient(
            timeout=bounded_timeout(timeout),
            follow_redirects=False,
            headers=headers or {},
        ) as client,
        client.stream(method.upper(), url, json=json_body) as response,
    ):
        status = response.status_code
        if 300 <= status < 400:
            raise OutboundHttpError(
                "redirects are not allowed",
                kind="redirect",
                status_code=status,
            )
        if status >= 400 and status not in allowed:
            raise OutboundHttpError(
                f"http_{status}",
                kind="http",
                status_code=status,
            )
        raw = await read_bounded_body(response, max_bytes=max_bytes)

    if status >= 400 and status in allowed:
        if not raw.strip():
            return status, None
        try:
            return status, parse_json_bytes(raw, sanitize=sanitize)
        except OutboundHttpError:
            return status, None
    return status, parse_json_bytes(raw, sanitize=sanitize)
