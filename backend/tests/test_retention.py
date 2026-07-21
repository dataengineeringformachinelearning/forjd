"""Retention sweep worker — unit tests (mocked pool)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from app.services import retention


def _pool(result: str = "DELETE 0") -> MagicMock:
    pool = MagicMock()
    pool.execute = AsyncMock(return_value=result)
    return pool


class TestTickRetention(unittest.IsolatedAsyncioTestCase):
    async def test_sweeps_all_retention_tables(self) -> None:
        pool = _pool()
        deleted = await retention.tick_retention(pool)
        self.assertEqual(
            set(deleted),
            {"telemetry_events", "stream_results", "crypto_sessions", "ingest_receipts"},
        )
        queries = [call.args[0] for call in pool.execute.await_args_list]
        self.assertEqual(len(queries), 4)
        for query in queries:
            # Bounded batches only — a sweep must never take unbounded locks.
            self.assertIn("LIMIT", query)
            self.assertIn("ctid IN", query)

    async def test_parses_deleted_counts(self) -> None:
        pool = _pool("DELETE 42")
        deleted = await retention.tick_retention(pool)
        self.assertEqual(deleted["telemetry_events"], 42)

    async def test_only_completed_receipts_are_deleted(self) -> None:
        pool = _pool()
        await retention.tick_retention(pool)
        receipts_query = pool.execute.await_args_list[3].args[0]
        self.assertIn("status = 'completed'", receipts_query)


if __name__ == "__main__":
    unittest.main()
