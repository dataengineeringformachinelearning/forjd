"""ASGI-level ingest request budget regression tests."""

from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import AsyncMock

from pydantic import ValidationError

from app.api.v1.capabilities import build_capability_document
from app.core.ingest_body_limit import IngestBodyLimitMiddleware
from app.core.ingest_limits import MAX_INGEST_BATCH_EVENTS, MAX_INGEST_BODY_BYTES
from app.models.ingest import IngestBatchRequest, IngestEventRequest


class IngestBodyLimitTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _scope(
        *,
        path: str = "/api/v1/ingest/events:batch",
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers or [],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 443),
            "state": {},
        }

    async def _exercise(
        self,
        *,
        messages: list[dict[str, Any]],
        headers: list[tuple[bytes, bytes]] | None = None,
        path: str = "/api/v1/ingest/events:batch",
        limit: int = 10,
    ) -> tuple[list[dict[str, Any]], AsyncMock, AsyncMock, dict[str, Any]]:
        downstream = AsyncMock()
        middleware = IngestBodyLimitMiddleware(
            downstream,
            paths={"/api/v1/ingest/events:batch"},
            max_body_bytes=limit,
        )
        receive = AsyncMock(side_effect=messages)
        sent: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        scope = self._scope(path=path, headers=headers)
        await middleware(scope, receive, send)
        return sent, receive, downstream, scope

    async def test_content_length_over_limit_returns_413_without_reading_body(self) -> None:
        sent, receive, downstream, _scope = await self._exercise(
            messages=[],
            headers=[(b"content-length", b"11")],
        )

        self.assertEqual(sent[0]["status"], 413)
        body = json.loads(sent[1]["body"])
        self.assertEqual(body["code"], "ingest_body_too_large")
        self.assertEqual(body["limit_bytes"], 10)
        receive.assert_not_awaited()
        downstream.assert_not_awaited()

    async def test_chunked_body_over_limit_returns_413_before_downstream(self) -> None:
        sent, receive, downstream, _scope = await self._exercise(
            messages=[
                {"type": "http.request", "body": b"123456", "more_body": True},
                {"type": "http.request", "body": b"78901", "more_body": False},
            ]
        )

        self.assertEqual(sent[0]["status"], 413)
        self.assertEqual(receive.await_count, 2)
        downstream.assert_not_awaited()

    async def test_bounded_body_is_replayed_unchanged_and_measured(self) -> None:
        seen: list[dict[str, Any]] = []

        async def downstream(scope: dict[str, Any], receive: Any, send: Any) -> None:
            seen.append(await receive())
            seen.append(await receive())
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = IngestBodyLimitMiddleware(
            downstream,
            paths={"/api/v1/ingest/events:batch"},
            max_body_bytes=10,
        )
        messages = [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"67890", "more_body": False},
        ]
        receive = AsyncMock(side_effect=messages)
        sent: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        scope = self._scope(headers=[(b"content-length", b"10")])
        await middleware(scope, receive, send)

        self.assertEqual(seen, messages)
        self.assertEqual(scope["state"]["ingest_body_bytes"], 10)
        self.assertEqual(sent[0]["status"], 204)

    async def test_non_ingest_route_bypasses_ingest_budget(self) -> None:
        _sent, receive, downstream, _scope = await self._exercise(
            path="/api/v1/reports/documents",
            headers=[(b"content-length", b"1000000")],
            messages=[],
        )
        downstream.assert_awaited_once()
        receive.assert_not_awaited()

    async def test_invalid_content_length_returns_400(self) -> None:
        sent, receive, downstream, _scope = await self._exercise(
            headers=[(b"content-length", b"ten")],
            messages=[],
        )
        self.assertEqual(sent[0]["status"], 400)
        receive.assert_not_awaited()
        downstream.assert_not_awaited()


class IngestBudgetContractTests(unittest.TestCase):
    def test_batch_model_enforces_lower_event_limit(self) -> None:
        event = IngestEventRequest.model_construct()
        IngestBatchRequest(events=[event] * MAX_INGEST_BATCH_EVENTS)
        with self.assertRaises(ValidationError):
            IngestBatchRequest(events=[event] * (MAX_INGEST_BATCH_EVENTS + 1))

    def test_capability_document_advertises_hard_limits(self) -> None:
        document = build_capability_document({"paths": {}})
        limits = document["limits"]
        self.assertEqual(limits["ingest_batch_events"], MAX_INGEST_BATCH_EVENTS)
        self.assertEqual(limits["ingest_request_bytes"], MAX_INGEST_BODY_BYTES)
