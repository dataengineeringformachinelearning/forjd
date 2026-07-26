"""JSON log formatter deep-scrubs secrets (ADR-0017)."""

from __future__ import annotations

import json
import logging
import unittest

from app.core.logging import JsonFormatter


class JsonFormatterScrubTests(unittest.TestCase):
    def test_scrubs_message_and_extras(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="forjd.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="auth failed Bearer abc.def.ghi fjsvc_ABCDEFGHijklmnop",
            args=(),
            exc_info=None,
        )
        record.access_token = "super-secret"  # noqa: B903 — LogRecord attr
        line = formatter.format(record)
        payload = json.loads(line)
        self.assertNotIn("Bearer abc", payload["message"])
        self.assertNotIn("fjsvc_ABCDEFGH", payload["message"])
        self.assertIn("[Filtered]", payload["message"])
        self.assertEqual(payload["access_token"], "[Filtered]")


if __name__ == "__main__":
    unittest.main()
