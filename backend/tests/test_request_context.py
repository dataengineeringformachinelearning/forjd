"""Request correlation and structured logging regression tests."""

from __future__ import annotations

import json
import logging
import unittest

from app.core.logging import JsonFormatter
from app.core.request_context import RequestContextMiddleware, valid_request_id


class TestRequestIdValidation(unittest.TestCase):
    def test_accepts_uuid_and_rejects_header_injection(self) -> None:
        self.assertTrue(valid_request_id("019f7931-dc31-7023-a820-a79a6fc555e6"))
        self.assertTrue(valid_request_id("deml_01J7ABCD12345678"))
        self.assertFalse(valid_request_id("short"))
        self.assertFalse(valid_request_id("trusted\r\nx-leak: yes"))


class TestRequestContextMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_echoes_valid_request_id_and_adds_timing(self) -> None:
        messages: list[dict] = []

        async def target(scope, receive, send):
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [(b"x-request-id", b"deml_01J7ABCD12345678")],
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await RequestContextMiddleware(target)(scope, receive, send)
        headers = dict(messages[0]["headers"])
        self.assertEqual(headers[b"x-request-id"], b"deml_01J7ABCD12345678")
        self.assertTrue(headers[b"server-timing"].startswith(b"app;dur="))

    async def test_replaces_invalid_request_id(self) -> None:
        messages: list[dict] = []

        async def target(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [(b"x-request-id", b"bad")],
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await RequestContextMiddleware(target)(scope, receive, send)
        generated = dict(messages[0]["headers"])[b"x-request-id"].decode()
        self.assertTrue(valid_request_id(generated))
        self.assertNotEqual(generated, "bad")


class TestJsonFormatter(unittest.TestCase):
    def test_emits_parseable_json_for_control_characters(self) -> None:
        record = logging.LogRecord(
            name="forjd.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='line one\n"line two"',
            args=(),
            exc_info=None,
        )
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual(payload["message"], 'line one\n"line two"')
        self.assertEqual(payload["logger"], "forjd.test")


if __name__ == "__main__":
    unittest.main()
