"""Shared dependency-client recovery tests."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.clients import create_redis_client


class TestRedisStartupRecovery(unittest.IsolatedAsyncioTestCase):
    async def test_retains_lazy_client_after_startup_race(self) -> None:
        client = MagicMock()
        client.ping = AsyncMock(side_effect=ConnectionError("not ready"))
        with (
            patch("app.core.clients.prefer_fly_ipv6_url", return_value="redis://local/0"),
            patch("app.core.clients.aioredis.from_url", return_value=client),
        ):
            result = await create_redis_client()

        self.assertIs(result, client)
        client.ping.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
