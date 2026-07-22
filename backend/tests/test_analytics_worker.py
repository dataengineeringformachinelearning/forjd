"""Analytics rollup + ML refresh worker — unit tests (mocked pool)."""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import analytics_worker

TENANT_ID = uuid.uuid4()


def _pool_with_active_tenants(tenant_ids: list[uuid.UUID]) -> MagicMock:
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[{"tenant_id": str(t)} for t in tenant_ids])
    pool.fetchval = AsyncMock(return_value=None)
    return pool


class TestActiveTenants(unittest.IsolatedAsyncioTestCase):
    async def test_returns_uuid_list(self) -> None:
        pool = _pool_with_active_tenants([TENANT_ID])
        tenants = await analytics_worker._active_tenants(pool)
        self.assertEqual(tenants, [TENANT_ID])
        # Fresh stream_results window + longer recent-activity window.
        self.assertEqual(
            pool.fetch.await_args.args[1:],
            (
                analytics_worker.ACTIVE_WINDOW_HOURS,
                analytics_worker.RECENT_TENANT_WINDOW_HOURS,
            ),
        )

    async def test_empty_when_no_recent_activity(self) -> None:
        pool = _pool_with_active_tenants([])
        self.assertEqual(await analytics_worker._active_tenants(pool), [])


class TestTick(unittest.IsolatedAsyncioTestCase):
    async def test_rollup_covers_previous_and_current_hour(self) -> None:
        pool = _pool_with_active_tenants([TENANT_ID])
        with (
            patch.object(analytics_worker.analytics_svc, "aggregate_hour", new=AsyncMock()) as agg,
            patch.object(analytics_worker, "_refresh_ml_scores", new=AsyncMock()) as refresh,
        ):
            count = await analytics_worker.tick_analytics_rollups(pool)
        self.assertEqual(count, 1)
        self.assertEqual(agg.await_count, 2)
        buckets = [call.kwargs["bucket_start"] for call in agg.await_args_list]
        self.assertEqual(buckets[1] - buckets[0], timedelta(hours=1))
        for bucket in buckets:
            self.assertEqual((bucket.minute, bucket.second), (0, 0))
        refresh.assert_awaited_once()

    async def test_ml_refresh_failure_does_not_block_rollups(self) -> None:
        pool = _pool_with_active_tenants([TENANT_ID])
        with (
            patch.object(analytics_worker.analytics_svc, "aggregate_hour", new=AsyncMock()) as agg,
            patch.object(
                analytics_worker,
                "_refresh_ml_scores",
                new=AsyncMock(side_effect=RuntimeError("sklearn broke")),
            ),
        ):
            count = await analytics_worker.tick_analytics_rollups(pool)
        self.assertEqual(count, 1)
        self.assertEqual(agg.await_count, 2)


class TestMlRefreshGuards(unittest.IsolatedAsyncioTestCase):
    async def test_skips_when_sklearn_missing(self) -> None:
        pool = MagicMock()
        with (
            patch.object(analytics_worker, "sklearn_available", return_value=False),
            patch.object(
                analytics_worker.ml_store, "features_from_stream_results", new=AsyncMock()
            ) as feats,
        ):
            await analytics_worker._refresh_ml_scores(pool, TENANT_ID)
        feats.assert_not_awaited()

    async def test_skips_when_scores_are_fresh(self) -> None:
        pool = MagicMock()
        pool.fetchval = AsyncMock(return_value=datetime.now(UTC))
        with (
            patch.object(analytics_worker, "sklearn_available", return_value=True),
            patch.object(
                analytics_worker.ml_store, "features_from_stream_results", new=AsyncMock()
            ) as feats,
        ):
            await analytics_worker._refresh_ml_scores(pool, TENANT_ID)
        feats.assert_not_awaited()

    async def test_skips_when_too_few_samples(self) -> None:
        pool = MagicMock()
        pool.fetchval = AsyncMock(return_value=None)
        with (
            patch.object(analytics_worker, "sklearn_available", return_value=True),
            patch.object(
                analytics_worker.ml_store,
                "features_from_stream_results",
                new=AsyncMock(return_value=[[0.1] * 6] * 3),
            ),
            patch.object(analytics_worker.ml_sb, "persist_fit", new=AsyncMock()) as persist,
        ):
            await analytics_worker._refresh_ml_scores(pool, TENANT_ID)
        persist.assert_not_awaited()

    async def test_fits_scores_and_persists_when_stale(self) -> None:
        pool = MagicMock()
        pool.fetchval = AsyncMock(return_value=datetime.now(UTC) - timedelta(days=2))
        feats = [[0.1, 0.0, 12.0, 0.5, 1.0, 0.3]] * 10
        fit_result = {"ok": True, "family": "classical_anomaly"}
        score_result = {"ok": True, "results": [{"score": 0.4, "is_anomaly": False}]}
        with (
            patch.object(analytics_worker, "sklearn_available", return_value=True),
            patch.object(
                analytics_worker.ml_store,
                "features_from_stream_results",
                new=AsyncMock(return_value=feats),
            ),
            patch("app.services.ml.classical_anomaly.fit", return_value=fit_result) as fit,
            patch("app.services.ml.classical_anomaly.score", return_value=score_result) as score,
            patch.object(analytics_worker.ml_sb, "persist_fit", new=AsyncMock()) as pfit,
            patch.object(analytics_worker.ml_sb, "persist_score", new=AsyncMock()) as pscore,
        ):
            await analytics_worker._refresh_ml_scores(pool, TENANT_ID)
        fit.assert_called_once()
        score.assert_called_once()
        pfit.assert_awaited_once()
        pscore.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
