"""Advisory worker lease helper."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from app.core.worker_lease import try_worker_lease


class TestWorkerLease(unittest.IsolatedAsyncioTestCase):
    async def test_yields_true_when_lock_acquired(self) -> None:
        pool = MagicMock()
        conn = MagicMock()
        conn.fetchval = AsyncMock(side_effect=[True, True])
        pool.acquire = AsyncMock(return_value=conn)
        pool.release = AsyncMock()

        async with try_worker_lease(pool, "forjd:worker:test") as leased:
            self.assertTrue(leased)

        self.assertEqual(conn.fetchval.await_count, 2)
        pool.release.assert_awaited_once_with(conn)

    async def test_yields_false_when_lock_busy(self) -> None:
        pool = MagicMock()
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value=False)
        pool.acquire = AsyncMock(return_value=conn)
        pool.release = AsyncMock()

        async with try_worker_lease(pool, "forjd:worker:test") as leased:
            self.assertFalse(leased)

        # No unlock when never leased.
        self.assertEqual(conn.fetchval.await_count, 1)
        pool.release.assert_awaited_once_with(conn)


if __name__ == "__main__":
    unittest.main()
