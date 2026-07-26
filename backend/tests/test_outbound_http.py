"""Bounded outbound HTTP helpers (ADR-0018)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.core.outbound_http import (
    OutboundHttpError,
    expect_list_of_dicts,
    parse_json_bytes,
    read_bounded_body,
)


class ParseJsonBytesTests(unittest.TestCase):
    def test_parses_and_sanitizes(self) -> None:
        raw = b'{"Name": "<b>Acme</b>", "Authorization": "Bearer x"}'
        out = parse_json_bytes(raw)
        assert isinstance(out, dict)
        self.assertEqual(out["Name"], "Acme")
        self.assertEqual(out["Authorization"], "[Filtered]")

    def test_rejects_invalid_json(self) -> None:
        with self.assertRaises(OutboundHttpError) as ctx:
            parse_json_bytes(b"not-json")
        self.assertEqual(ctx.exception.kind, "json")


class ShapeGuardTests(unittest.TestCase):
    def test_expect_list_of_dicts(self) -> None:
        self.assertEqual(expect_list_of_dicts("x"), [])
        self.assertEqual(
            expect_list_of_dicts([{"a": 1}, "skip", {"b": 2}], max_items=10),
            [{"a": 1}, {"b": 2}],
        )


class ReadBoundedBodyTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_oversized_stream(self) -> None:
        response = MagicMock()
        response.status_code = 200
        response.headers = {}

        async def _chunks():
            yield b"x" * 100
            yield b"y" * 100

        response.aiter_bytes = lambda: _chunks()
        with self.assertRaises(OutboundHttpError) as ctx:
            await read_bounded_body(response, max_bytes=150)
        self.assertEqual(ctx.exception.kind, "too_large")

    async def test_rejects_redirect_status(self) -> None:
        response = MagicMock()
        response.status_code = 302
        response.headers = {}
        with self.assertRaises(OutboundHttpError) as ctx:
            await read_bounded_body(response)
        self.assertEqual(ctx.exception.kind, "redirect")


if __name__ == "__main__":
    unittest.main()
