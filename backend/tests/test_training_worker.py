"""Scheduled ML training + HF publishing worker — unit tests (mocked pool)."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import training_worker

TENANT_ID = uuid.uuid4()


def _pool(rows: list[dict[str, str]] | None = None) -> MagicMock:
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows or [])
    return pool


class TestTenantsDueTraining(unittest.IsolatedAsyncioTestCase):
    async def test_returns_uuid_list(self) -> None:
        pool = _pool([{"tenant_id": str(TENANT_ID)}])
        due = await training_worker._tenants_due_training(pool)
        self.assertEqual(due, [TENANT_ID])

    async def test_empty_when_all_models_fresh(self) -> None:
        pool = _pool([])
        self.assertEqual(await training_worker._tenants_due_training(pool), [])


class TestScoreSeries(unittest.IsolatedAsyncioTestCase):
    async def test_short_series_returns_none(self) -> None:
        pool = _pool([{"score": 0.5}] * 5)
        self.assertIsNone(await training_worker._score_series(pool, TENANT_ID))

    async def test_long_series_reversed_to_ascending(self) -> None:
        rows = [{"score": float(i)} for i in range(training_worker.MIN_SERIES_LEN)]
        pool = _pool(rows)
        series = await training_worker._score_series(pool, TENANT_ID)
        assert series is not None
        self.assertEqual(series[0], float(training_worker.MIN_SERIES_LEN - 1))
        self.assertEqual(series[-1], 0.0)


class TestTick(unittest.IsolatedAsyncioTestCase):
    async def test_skips_when_torch_unavailable(self) -> None:
        pool = _pool()
        with patch.object(training_worker, "torch_available", return_value=False):
            self.assertEqual(await training_worker.tick_training(pool), 0)
        pool.fetch.assert_not_awaited()

    async def test_one_tenant_failure_does_not_block_others(self) -> None:
        other = uuid.uuid4()
        pool = _pool()
        with (
            patch.object(training_worker, "torch_available", return_value=True),
            patch.object(
                training_worker,
                "_tenants_due_training",
                new=AsyncMock(return_value=[TENANT_ID, other]),
            ),
            patch.object(
                training_worker,
                "_train_tenant",
                new=AsyncMock(side_effect=[RuntimeError("boom"), {"sla": True}]),
            ) as train,
            patch.object(training_worker, "_hf_configured", return_value=False),
        ):
            count = await training_worker.tick_training(pool)
        self.assertEqual(count, 2)
        self.assertEqual(train.await_count, 2)

    async def test_hf_publish_called_only_when_configured(self) -> None:
        pool = _pool()
        with (
            patch.object(training_worker, "torch_available", return_value=True),
            patch.object(
                training_worker,
                "_tenants_due_training",
                new=AsyncMock(return_value=[TENANT_ID]),
            ),
            patch.object(training_worker, "_train_tenant", new=AsyncMock(return_value={})),
            patch.object(training_worker, "_hf_configured", return_value=True),
            patch.object(training_worker, "_publish_tenant_artifacts", return_value=3) as pub,
        ):
            await training_worker.tick_training(pool)
        pub.assert_called_once_with(TENANT_ID)

    async def test_hf_publish_failure_does_not_fail_tick(self) -> None:
        pool = _pool()
        with (
            patch.object(training_worker, "torch_available", return_value=True),
            patch.object(
                training_worker,
                "_tenants_due_training",
                new=AsyncMock(return_value=[TENANT_ID]),
            ),
            patch.object(training_worker, "_train_tenant", new=AsyncMock(return_value={})),
            patch.object(training_worker, "_hf_configured", return_value=True),
            patch.object(
                training_worker,
                "_publish_tenant_artifacts",
                side_effect=RuntimeError("hub down"),
            ),
        ):
            self.assertEqual(await training_worker.tick_training(pool), 1)


class TestTenantHash(unittest.TestCase):
    def test_hash_is_stable_and_opaque(self) -> None:
        hashed = training_worker._tenant_hash(TENANT_ID)
        self.assertEqual(len(hashed), 16)
        self.assertNotIn(str(TENANT_ID)[:8], hashed)
        self.assertEqual(hashed, training_worker._tenant_hash(TENANT_ID))


if __name__ == "__main__":
    unittest.main()
