"""Bounded retry for informational engine version probe."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services import engine as engine_svc


class TestRemoteVersion(unittest.IsolatedAsyncioTestCase):
    async def test_retries_once_then_succeeds(self) -> None:
        calls = {"n": 0}

        async def _flaky(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("engine warm-up")
            return {"service": "forjd-engine", "version": "0.3.0"}

        with (
            patch.object(engine_svc, "_http_configured", return_value=True),
            patch.object(engine_svc, "_http_json", side_effect=_flaky),
            patch("app.services.engine.asyncio.sleep", new=AsyncMock()),
        ):
            result = await engine_svc.remote_version()

        self.assertEqual(result, {"service": "forjd-engine", "version": "0.3.0"})
        self.assertEqual(calls["n"], 2)

    async def test_returns_error_payload_after_retries(self) -> None:
        with (
            patch.object(engine_svc, "_http_configured", return_value=True),
            patch.object(
                engine_svc,
                "_http_json",
                side_effect=RuntimeError("down"),
            ),
            patch("app.services.engine.asyncio.sleep", new=AsyncMock()),
        ):
            result = await engine_svc.remote_version()

        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result["ok"])
        self.assertIn("down", str(result["error"]))


if __name__ == "__main__":
    unittest.main()
