"""ASGI-level hard cap for canonical ingest bodies before JSON validation."""

from __future__ import annotations

from collections.abc import Collection

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.ingest_limits import MAX_INGEST_BODY_BYTES


class IngestBodyLimitMiddleware:
    """Reject oversized ingest bodies before FastAPI/Pydantic materializes JSON.

    ``Content-Length`` permits a zero-read rejection. Chunked or otherwise
    unbounded requests are pre-buffered only up to the same hard limit and then
    replayed unchanged to the downstream ASGI application.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        paths: Collection[str],
        max_body_bytes: int = MAX_INGEST_BODY_BYTES,
    ) -> None:
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self.app = app
        self.paths = frozenset(path.rstrip("/") for path in paths)
        self.max_body_bytes = max_body_bytes

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        values = [
            value.strip()
            for name, value in scope.get("headers", [])
            if name.lower() == b"content-length"
        ]
        if not values:
            return None
        try:
            parsed = [int(value.decode("ascii")) for value in values]
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("invalid Content-Length") from exc
        if any(value < 0 for value in parsed) or len(set(parsed)) != 1:
            raise ValueError("invalid Content-Length")
        return parsed[0]

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "detail": "ingest request body exceeds the hard byte limit",
                "code": "ingest_body_too_large",
                "limit_bytes": self.max_body_bytes,
            },
            headers={"X-Max-Body-Bytes": str(self.max_body_bytes)},
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or str(scope.get("method", "")).upper() != "POST"
            or str(scope.get("path", "")).rstrip("/") not in self.paths
        ):
            await self.app(scope, receive, send)
            return

        try:
            content_length = self._content_length(scope)
        except ValueError:
            response = JSONResponse(
                status_code=400,
                content={"detail": "invalid Content-Length"},
            )
            await response(scope, receive, send)
            return
        if content_length is not None and content_length > self.max_body_bytes:
            await self._reject(scope, receive, send)
            return

        buffered: list[Message] = []
        received_bytes = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message["type"] != "http.request":
                break
            body = message.get("body", b"")
            if not isinstance(body, bytes):
                body = bytes(body)
            received_bytes += len(body)
            if received_bytes > self.max_body_bytes:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["ingest_body_bytes"] = received_bytes

        async def replay_receive() -> Message:
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)
