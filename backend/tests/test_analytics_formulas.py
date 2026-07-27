"""Unit tests for CES / percentile analytics formulas."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.core.auth import AuthUser, PrincipalKind
from app.services import analytics as analytics_svc
from app.services.analytics import (
    _bucket_label,
    _spiking_temporal_forecast,
    _weighted_anomaly_rate,
    ces_composite,
    percentile_index,
    uptime_status,
)


class TestAnalyticsFormulas(unittest.TestCase):
    def test_percentile_index(self) -> None:
        self.assertEqual(percentile_index(100, 0.99), 98)
        self.assertEqual(percentile_index(0), 0)

    def test_uptime_status(self) -> None:
        self.assertEqual(uptime_status(1.0), "operational")
        self.assertEqual(uptime_status(0.995), "degraded")
        self.assertEqual(uptime_status(0.96), "partial_outage")
        self.assertEqual(uptime_status(0.5), "major_outage")

    def test_ces_composite_bounds(self) -> None:
        out = ces_composite(uptime_pct=99.0, incidents=1, p99_ms=200.0)
        self.assertGreaterEqual(out["ces_level"], 0.0)
        self.assertLessEqual(out["ces_level"], 100.0)

    def test_bucket_label(self) -> None:
        self.assertEqual(_bucket_label("2026-07-19T14:00:00+00:00"), "14:00")

    def test_spiking_forecast_empty_and_rising(self) -> None:
        self.assertIsNone(_spiking_temporal_forecast([]))
        # No threat/error pressure is an absent signal, not Spike Risk 0.00.
        flat = [
            {"threats_detected": 0, "error_rate_percent": 0.0},
            {"threats_detected": 0, "error_rate_percent": 0.0},
        ]
        self.assertIsNone(_spiking_temporal_forecast(flat))
        # Newest-first (same order as overview SQL).
        rising_desc = [
            {"threats_detected": 6, "error_rate_percent": 25.0},
            {"threats_detected": 4, "error_rate_percent": 20.0},
            {"threats_detected": 0, "error_rate_percent": 0.0},
            {"threats_detected": 0, "error_rate_percent": 0.0},
        ]
        score = _spiking_temporal_forecast(rising_desc)
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 100.0)
        # Probe failure rate is endpoint uptime, not a security anomaly signal.
        probe_failures_only = [
            {
                "threats_detected": 0,
                "error_rate_percent": 100.0,
                "metadata": {"anomaly_rate_percent": 0.0},
            },
            {
                "threats_detected": 0,
                "error_rate_percent": 100.0,
                "metadata": {"anomaly_rate_percent": 0.0},
            },
        ]
        self.assertIsNone(_spiking_temporal_forecast(probe_failures_only))

    def test_anomaly_rate_is_weighted_by_request_volume(self) -> None:
        rows = [
            {
                "total_requests": 1,
                "error_rate_percent": 100.0,
                "metadata": {"anomaly_count": 1, "anomaly_rate_percent": 100.0},
            },
            {
                "total_requests": 999,
                "error_rate_percent": 0.0,
                "metadata": {"anomaly_count": 0, "anomaly_rate_percent": 0.0},
            },
        ]
        self.assertEqual(_weighted_anomaly_rate(rows), 0.1)


class TestAggregateHour(unittest.IsolatedAsyncioTestCase):
    async def _aggregate(
        self,
        latency_row: dict[str, float | int],
        *,
        total_requests: int = 4,
        anomaly_count: int = 1,
    ) -> tuple[MagicMock, dict[str, object]]:
        tenant_id = uuid4()
        bucket_start = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
        pool = MagicMock()
        inserted = {
            "id": str(uuid4()),
            "tenant_id": str(tenant_id),
            "bucket_start": bucket_start,
            "total_requests": total_requests,
            "avg_latency_ms": latency_row["avg_latency_ms"],
            "p99_latency_ms": latency_row["p99_latency_ms"],
            "error_rate_percent": (
                anomaly_count / total_requests * 100.0 if total_requests else 0.0
            ),
            "threats_detected": 2,
            "active_incidents": 1,
            "unique_visitors": 3,
        }
        pool.fetchrow = AsyncMock(
            side_effect=[
                {"total_requests": total_requests, "anomaly_count": anomaly_count},
                latency_row,
                inserted,
            ]
        )
        pool.fetchval = AsyncMock(side_effect=[2, 1])
        distributions = {
            "unique_visitors": 3,
            "origin_distribution": [{"region": "iad", "count": 4}],
            "endpoint_counts": [{"endpoint": "status.widget", "count": 4}],
            "http_statuses": [{"status": "2xx", "count": 4}],
        }
        with (
            patch.object(analytics_svc, "ensure_analytics_schema", new=AsyncMock()),
            patch.object(
                analytics_svc,
                "_routing_distributions",
                new=AsyncMock(return_value=distributions),
            ),
        ):
            result = await analytics_svc.aggregate_hour(
                pool,
                tenant_id=tenant_id,
                bucket_start=bucket_start,
            )

        self.assertTrue(result["ok"])
        return pool, result["bucket"]

    async def test_probe_only_tenant_uses_measured_latency_and_uptime(self) -> None:
        pool, bucket = await self._aggregate(
            {
                "sample_count": 5,
                "active_count": 4,
                "avg_latency_ms": 12.5,
                "p99_latency_ms": 42.0,
            },
            total_requests=0,
            anomaly_count=0,
        )

        stats_call = pool.fetchrow.await_args_list[0]
        latency_call = pool.fetchrow.await_args_list[1]
        self.assertIn("FROM health_probe_observations", latency_call.args[0])
        self.assertIn("observed_at >= $2 AND observed_at < $3", latency_call.args[0])
        self.assertEqual(latency_call.args[1:], stats_call.args[1:])
        insert_args = pool.fetchrow.await_args_list[2].args
        self.assertEqual(insert_args[3], 0)
        self.assertEqual(insert_args[4], 12.5)
        self.assertEqual(insert_args[5], 42.0)
        self.assertEqual(insert_args[6], 0.0)
        metadata = json.loads(insert_args[10])
        self.assertEqual(metadata["latency_source"], "health_probe_observations")
        self.assertEqual(metadata["latency_sample_count"], 5)
        self.assertTrue(metadata["latency_data_available"])
        self.assertEqual(metadata["uptime_source"], "health_probe_observations")
        self.assertEqual(metadata["uptime_sample_count"], 5)
        self.assertEqual(metadata["uptime_active_count"], 4)
        self.assertEqual(metadata["uptime_percent"], 80.0)
        self.assertTrue(metadata["uptime_data_available"])
        self.assertEqual(metadata["anomaly_rate_percent"], 0.0)
        self.assertEqual(bucket["p99_latency_ms"], 42.0)
        self.assertEqual(bucket["uptime_pct"], 80.0)
        self.assertTrue(bucket["latency_data_available"])
        self.assertTrue(bucket["uptime_data_available"])
        self.assertEqual(bucket["error_rate_percent"], 0.0)

    async def test_no_probes_store_only_an_explicit_unavailable_sentinel(self) -> None:
        pool, bucket = await self._aggregate(
            {
                "sample_count": 0,
                "active_count": 0,
                "avg_latency_ms": 0.0,
                "p99_latency_ms": 0.0,
            }
        )

        stats_query = pool.fetchrow.await_args_list[0].args[0]
        self.assertNotIn("AVG(score)", stats_query)
        insert_args = pool.fetchrow.await_args_list[2].args
        self.assertEqual(insert_args[4], 0.0)
        self.assertEqual(insert_args[5], 0.0)
        self.assertEqual(insert_args[6], 25.0)
        metadata = json.loads(insert_args[10])
        self.assertEqual(metadata["latency_sample_count"], 0)
        self.assertFalse(metadata["latency_data_available"])
        self.assertEqual(metadata["uptime_sample_count"], 0)
        self.assertEqual(metadata["uptime_active_count"], 0)
        self.assertIsNone(metadata["uptime_percent"])
        self.assertFalse(metadata["uptime_data_available"])
        self.assertEqual(metadata["anomaly_rate_percent"], 25.0)
        self.assertIsNone(bucket["avg_latency_ms"])
        self.assertIsNone(bucket["p99_latency_ms"])
        self.assertIsNone(bucket["uptime_pct"])
        self.assertFalse(bucket["latency_data_available"])
        self.assertFalse(bucket["uptime_data_available"])
        self.assertEqual(bucket["error_rate_percent"], 25.0)


class TestAnalyticsOverviewFallback(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_probe_only_tenant_is_available_before_first_rollup(self) -> None:
        tenant_id = uuid4()
        pool = MagicMock()
        pool.fetch = AsyncMock(side_effect=[[], []])
        pool.fetchrow = AsyncMock(
            return_value={
                "sample_count": 3,
                "active_count": 3,
                "avg_latency_ms": 2.0,
                "p99_latency_ms": 3.0,
            }
        )
        user = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(tenant_id),
            scopes=frozenset({"analytics:read"}),
        )
        with (
            patch.object(analytics_svc.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(analytics_svc, "ensure_analytics_schema", new=AsyncMock()),
            patch.object(
                analytics_svc,
                "_latest_temporal_signal",
                new=AsyncMock(
                    return_value={
                        "spiking_temporal_forecast": None,
                        "temporal_status": "insufficient_data",
                    }
                ),
            ),
            patch.object(
                analytics_svc,
                "_latest_predicted_sla",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.ml.store.list_recent_training_runs",
                new=AsyncMock(return_value=[]),
            ),
        ):
            out = await analytics_svc.overview(pool, user=user, tenant_id=tenant_id)

        self.assertTrue(out["data_available"])
        self.assertTrue(out["latency_data_available"])
        self.assertTrue(out["uptime_data_available"])
        self.assertEqual(out["p99_latency_ms"], 3.0)
        self.assertEqual(out["uptime_pct"], 100.0)
        self.assertEqual(out["status"], "operational")
        self.assertEqual(out["time_series"], [])
        self.assertGreater(out["ces"]["ces_level"], 0.0)

    async def test_overview_falls_back_to_recent_buckets_when_24h_empty(self) -> None:
        tenant_id = uuid4()
        older = datetime(2026, 7, 20, 22, 0, tzinfo=UTC)
        row = {
            "bucket_start": older,
            "total_requests": 24,
            "avg_latency_ms": 12.0,
            "p99_latency_ms": 40.0,
            "error_rate_percent": 0.0,
            "threats_detected": 0,
            "active_incidents": 0,
            "unique_visitors": 3,
            "metadata": {
                "latency_source": "health_probe_observations",
                "latency_sample_count": 4,
                "latency_data_available": True,
                "uptime_source": "health_probe_observations",
                "uptime_sample_count": 4,
                "uptime_active_count": 4,
                "uptime_percent": 100.0,
                "uptime_data_available": True,
                "origin_distribution": [{"region": "iad", "count": 10}],
                "http_statuses": [{"status": "2xx", "count": 20}],
                "endpoint_counts": [{"endpoint": "analytics.overview", "count": 8}],
            },
        }
        pool = MagicMock()
        pool.fetch = AsyncMock(side_effect=[[], [row]])
        pool.fetchrow = AsyncMock(
            return_value={
                "sample_count": 4,
                "active_count": 4,
                "avg_latency_ms": 12.0,
                "p99_latency_ms": 40.0,
            }
        )
        user = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(tenant_id),
            scopes=frozenset({"analytics:read"}),
        )
        with (
            patch.object(analytics_svc.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(analytics_svc, "ensure_analytics_schema", new=AsyncMock()),
            patch.object(
                analytics_svc,
                "_latest_temporal_signal",
                new=AsyncMock(
                    return_value={
                        "spiking_temporal_forecast": 42.5,
                        "temporal_status": "ready",
                        "temporal_backend": "norse_lif",
                        "temporal_sample_count": 64,
                        "temporal_scored_at": "2026-07-20T21:00:00+00:00",
                        "uses_norse": True,
                    }
                ),
            ),
            patch.object(
                analytics_svc,
                "_latest_predicted_sla",
                new=AsyncMock(return_value=97.25),
            ),
        ):
            out = await analytics_svc.overview(pool, user=user, tenant_id=tenant_id)
        self.assertEqual(out["total_requests"], 24)
        self.assertEqual(out["unique_visitors"], 3)
        self.assertEqual(out["p99_latency_ms"], 40.0)
        self.assertTrue(out["latency_data_available"])
        self.assertEqual(out["uptime_pct"], 100.0)
        self.assertTrue(out["uptime_data_available"])
        self.assertEqual(len(out["time_series"]), 1)
        self.assertEqual(out["time_series"][0]["latency"], 40.0)
        self.assertTrue(out["time_series"][0]["latency_data_available"])
        self.assertEqual(out["time_series"][0]["latency_sample_count"], 4)
        self.assertEqual(out["time_series"][0]["requests"], 24)
        self.assertEqual(out["uptime_series"][0]["uptime"], 100.0)
        self.assertTrue(out["uptime_series"][0]["uptime_data_available"])
        self.assertEqual(out["uptime_series"][0]["uptime_sample_count"], 4)
        self.assertGreater(out["ces"]["ces_level"], 0)
        self.assertEqual(out["origin_distribution"][0]["region"], "iad")
        self.assertEqual(out["http_statuses"][0]["status"], "2xx")
        self.assertEqual(out["endpoint_counts"][0]["endpoint"], "analytics.overview")
        self.assertEqual(out["ces"]["spiking_temporal_forecast"], 42.5)
        self.assertEqual(out["ces"]["temporal_status"], "ready")
        self.assertEqual(out["ces"]["temporal_backend"], "norse_lif")
        self.assertTrue(out["ces"]["uses_norse"])
        self.assertEqual(out["ces"]["predicted_sla"], 97.25)
        self.assertEqual(out["ces"]["average_sla"], 97.25)

    async def test_overview_weights_uptime_by_probe_sample_count(self) -> None:
        tenant_id = uuid4()
        rows = [
            {
                "bucket_start": datetime(2026, 7, 27, 12, 0, tzinfo=UTC),
                "total_requests": 0,
                "avg_latency_ms": 5.0,
                "p99_latency_ms": 5.0,
                "error_rate_percent": 0.0,
                "threats_detected": 0,
                "active_incidents": 0,
                "unique_visitors": 0,
                "metadata": {
                    "latency_source": "health_probe_observations",
                    "latency_sample_count": 1,
                    "uptime_source": "health_probe_observations",
                    "uptime_sample_count": 1,
                    "uptime_active_count": 1,
                    "anomaly_rate_percent": 0.0,
                },
            },
            {
                "bucket_start": datetime(2026, 7, 27, 11, 0, tzinfo=UTC),
                "total_requests": 0,
                "avg_latency_ms": 10.0,
                "p99_latency_ms": 10.0,
                "error_rate_percent": 100.0,
                "threats_detected": 0,
                "active_incidents": 0,
                "unique_visitors": 0,
                "metadata": {
                    "latency_source": "health_probe_observations",
                    "latency_sample_count": 9,
                    "uptime_source": "health_probe_observations",
                    "uptime_sample_count": 9,
                    "uptime_active_count": 0,
                    "anomaly_rate_percent": 0.0,
                },
            },
            {
                "bucket_start": datetime(2026, 7, 27, 10, 0, tzinfo=UTC),
                "total_requests": 100,
                "avg_latency_ms": 999.0,
                "p99_latency_ms": 999.0,
                "error_rate_percent": 99.0,
                "threats_detected": 0,
                "active_incidents": 0,
                "unique_visitors": 0,
                "metadata": {"source": "stream_results"},
            },
        ]
        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=rows)
        pool.fetchrow = AsyncMock(
            return_value={
                "sample_count": 10,
                "active_count": 1,
                "avg_latency_ms": 9.5,
                "p99_latency_ms": 10.0,
            }
        )
        user = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(tenant_id),
            scopes=frozenset({"analytics:read"}),
        )
        with (
            patch.object(analytics_svc.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(analytics_svc, "ensure_analytics_schema", new=AsyncMock()),
            patch.object(
                analytics_svc,
                "_latest_temporal_signal",
                new=AsyncMock(
                    return_value={
                        "spiking_temporal_forecast": None,
                        "temporal_status": "insufficient_data",
                    }
                ),
            ),
            patch.object(
                analytics_svc,
                "_latest_predicted_sla",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.ml.store.list_recent_training_runs",
                new=AsyncMock(return_value=[]),
            ),
        ):
            out = await analytics_svc.overview(pool, user=user, tenant_id=tenant_id)

        self.assertTrue(out["data_available"])
        self.assertTrue(out["uptime_data_available"])
        self.assertEqual(out["uptime_pct"], 10.0)
        self.assertEqual(out["status"], "major_outage")
        self.assertEqual(
            [point["uptime"] for point in out["uptime_series"]],
            [None, 0.0, 100.0],
        )
        self.assertEqual(
            [point["uptime_sample_count"] for point in out["uptime_series"]],
            [0, 9, 1],
        )
        self.assertEqual(
            [point["latency"] for point in out["time_series"]],
            [None, 10.0, 5.0],
        )

    async def test_overview_ignores_legacy_synthetic_latency_and_uptime(self) -> None:
        tenant_id = uuid4()
        row = {
            "bucket_start": datetime(2026, 7, 27, 12, 0, tzinfo=UTC),
            "total_requests": 24,
            "avg_latency_ms": 999.0,
            "p99_latency_ms": 999.0,
            "error_rate_percent": 0.0,
            "threats_detected": 0,
            "active_incidents": 0,
            "unique_visitors": 3,
            "metadata": {"source": "stream_results"},
        }
        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[row])
        pool.fetchrow = AsyncMock(
            return_value={
                "sample_count": 0,
                "active_count": 0,
                "avg_latency_ms": 0.0,
                "p99_latency_ms": 0.0,
            }
        )
        user = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(tenant_id),
            scopes=frozenset({"analytics:read"}),
        )
        with (
            patch.object(analytics_svc.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(analytics_svc, "ensure_analytics_schema", new=AsyncMock()),
            patch.object(
                analytics_svc,
                "_latest_temporal_signal",
                new=AsyncMock(
                    return_value={
                        "spiking_temporal_forecast": None,
                        "temporal_status": "insufficient_data",
                    }
                ),
            ),
            patch.object(
                analytics_svc,
                "_latest_predicted_sla",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.ml.store.list_recent_training_runs",
                new=AsyncMock(return_value=[]),
            ),
        ):
            out = await analytics_svc.overview(pool, user=user, tenant_id=tenant_id)

        self.assertTrue(out["data_available"])
        self.assertFalse(out["latency_data_available"])
        self.assertIsNone(out["p99_latency_ms"])
        self.assertFalse(out["uptime_data_available"])
        self.assertIsNone(out["uptime_pct"])
        self.assertEqual(out["status"], "unknown")
        self.assertIsNone(out["ces"]["ces_level"])
        self.assertIsNone(out["ces"]["ces_sla"])
        self.assertIsNone(out["ces"]["ces_stability"])
        self.assertEqual(out["total_requests"], 24)
        self.assertEqual(len(out["time_series"]), 1)
        self.assertIsNone(out["time_series"][0]["latency"])
        self.assertFalse(out["time_series"][0]["latency_data_available"])
        self.assertEqual(out["time_series"][0]["latency_sample_count"], 0)
        self.assertEqual(out["time_series"][0]["requests"], 24)
        self.assertIsNone(out["uptime_series"][0]["uptime"])
        self.assertFalse(out["uptime_series"][0]["uptime_data_available"])
        self.assertEqual(out["uptime_series"][0]["uptime_sample_count"], 0)


if __name__ == "__main__":
    unittest.main()
