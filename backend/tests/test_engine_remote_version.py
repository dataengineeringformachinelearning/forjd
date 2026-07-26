"""Bounded retry for informational engine version probe."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services import engine as engine_svc


@pytest.mark.asyncio
async def test_remote_version_retries_once_then_succeeds() -> None:
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

    assert result == {"service": "forjd-engine", "version": "0.3.0"}
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_remote_version_returns_error_payload_after_retries() -> None:
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

    assert result is not None
    assert result["ok"] is False
    assert "down" in str(result["error"])
