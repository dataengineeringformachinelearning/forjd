"""Correlation, worker ticks, and client-safe 500 bodies."""

from __future__ import annotations

import logging
import unittest
from unittest.mock import MagicMock, patch

from app.core.http_errors import unhandled_exception_handler
from app.core.request_context import request_id_var
from app.core.worker_logging import worker_tick
from app.services.engine import _correlation_headers


class TestWorkerTick(unittest.TestCase):
    def test_emits_duration_and_outcome_on_success(self) -> None:
        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        logger = logging.getLogger("forjd.test.worker_tick")
        logger.handlers = [_Capture()]
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        with worker_tick(logger, "analytics-rollup", level=logging.INFO) as tick:
            tick["tenants"] = 2

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].msg, "worker_tick")
        self.assertEqual(records[0].worker, "analytics-rollup")  # type: ignore[attr-defined]
        self.assertEqual(records[0].outcome, "ok")  # type: ignore[attr-defined]
        self.assertEqual(records[0].tenants, 2)  # type: ignore[attr-defined]
        self.assertGreaterEqual(records[0].duration_ms, 0)  # type: ignore[attr-defined]

    def test_logs_exception_and_reraises(self) -> None:
        logger = logging.getLogger("forjd.test.worker_tick_err")
        logger.handlers = []
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        with self.assertRaises(RuntimeError), worker_tick(logger, "analytics-rollup"):
            raise RuntimeError("boom")


class TestEngineCorrelationHeaders(unittest.TestCase):
    def test_forwards_valid_request_id(self) -> None:
        token = request_id_var.set("deml_01J7ABCD12345678")
        try:
            self.assertEqual(
                _correlation_headers(),
                {"X-Request-ID": "deml_01J7ABCD12345678"},
            )
        finally:
            request_id_var.reset(token)

    def test_skips_default_placeholder(self) -> None:
        token = request_id_var.set("-")
        try:
            self.assertEqual(_correlation_headers(), {})
        finally:
            request_id_var.reset(token)


class TestUnhandledExceptionRequestId(unittest.IsolatedAsyncioTestCase):
    async def test_500_body_includes_request_id(self) -> None:
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/v1/example"
        token = request_id_var.set("019f7931dc317023a820a79a6fc555e6")
        try:
            with (
                patch("app.core.http_errors.logger"),
                patch("app.core.http_errors.expose_error_details", return_value=False),
            ):
                response = await unhandled_exception_handler(request, RuntimeError("secret"))
            self.assertEqual(response.status_code, 500)
            body = response.body
            self.assertIn(b"request_id", body)
            self.assertIn(b"019f7931dc317023a820a79a6fc555e6", body)
            self.assertNotIn(b"secret", body)
            self.assertIn(b"request failed", body)
        finally:
            request_id_var.reset(token)


if __name__ == "__main__":
    unittest.main()
