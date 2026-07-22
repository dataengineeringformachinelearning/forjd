"""Unit tests for CES / percentile analytics formulas."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.core.auth import AuthUser, PrincipalKind
from app.services import analytics as analytics_svc
from app.services.analytics import (
    _bucket_label,
    _spiking_temporal_forecast,
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
        self.assertEqual(_spiking_temporal_forecast([]), 0.0)
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


class TestAnalyticsOverviewFallback(unittest.IsolatedAsyncioTestCase):
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
                "origin_distribution": [{"region": "iad", "count": 10}],
                "http_statuses": [{"status": "2xx", "count": 20}],
                "endpoint_counts": [{"endpoint": "analytics.overview", "count": 8}],
            },
        }
        pool = MagicMock()
        pool.fetch = AsyncMock(side_effect=[[], [row]])
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
        ):
            out = await analytics_svc.overview(pool, user=user, tenant_id=tenant_id)
        self.assertEqual(out["total_requests"], 24)
        self.assertEqual(out["unique_visitors"], 3)
        self.assertEqual(len(out["time_series"]), 1)
        self.assertEqual(out["time_series"][0]["requests"], 24)
        self.assertGreater(out["ces"]["ces_level"], 0)
        self.assertEqual(out["origin_distribution"][0]["region"], "iad")
        self.assertEqual(out["http_statuses"][0]["status"], "2xx")
        self.assertEqual(out["endpoint_counts"][0]["endpoint"], "analytics.overview")


if __name__ == "__main__":
    unittest.main()
