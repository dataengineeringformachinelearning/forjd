"""Unit tests for status page helpers."""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import status as status_svc
from app.services.status import (
    _day_status,
    _fill_uptime_history,
    _merge_day_stats,
    _overall_status,
    _page_dict,
    _public_page_dict,
    _resolve_probe_url,
    _uptime_from_history,
    public_slug_candidates,
    public_slug_prefix,
    slugify_identifier,
)


def _page_row() -> dict[str, Any]:
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "22222222-2222-2222-2222-222222222222",
        "slug": "acme-status",
        "title": "Acme",
        "description": "Public status",
        "is_published": True,
        "created_at": now,
        "updated_at": now,
    }


class TestOverallStatus(unittest.TestCase):
    def test_empty_operational(self) -> None:
        self.assertEqual(_overall_status([]), "operational")

    def test_worst_wins(self) -> None:
        self.assertEqual(
            _overall_status(["operational", "degraded", "major_outage"]),
            "major_outage",
        )


class TestPublicSlugCandidates(unittest.TestCase):
    def test_slugify_domain_style(self) -> None:
        self.assertEqual(slugify_identifier("joealongi.dev"), "joealongi-dev")

    def test_candidates_include_slugified_and_stem(self) -> None:
        self.assertEqual(
            public_slug_candidates("joealongi.dev"),
            ["joealongi-dev", "joealongi"],
        )

    def test_candidates_keep_canonical_slug(self) -> None:
        self.assertEqual(public_slug_candidates("joealongi-dev"), ["joealongi-dev"])

    def test_prefix_from_legacy_embed_stem(self) -> None:
        self.assertEqual(public_slug_prefix("joealongi"), "joealongi")
        self.assertEqual(public_slug_prefix("joealongi.dev"), "joealongi")
        self.assertIsNone(public_slug_prefix("ab"))


class TestPublicPageDict(unittest.TestCase):
    def test_authenticated_page_dict_includes_tenant_id(self) -> None:
        page = _page_dict(_page_row())
        self.assertEqual(page["tenant_id"], "22222222-2222-2222-2222-222222222222")
        self.assertEqual(page["slug"], "acme-status")

    def test_public_page_dict_omits_tenant_id(self) -> None:
        page = _public_page_dict(_page_row())
        self.assertNotIn("tenant_id", page)
        self.assertEqual(page["slug"], "acme-status")
        self.assertEqual(page["title"], "Acme")
        self.assertTrue(page["is_published"])


class TestUptimeHistoryHelpers(unittest.TestCase):
    def test_day_status_mapping(self) -> None:
        self.assertEqual(_day_status(0, 0), ("no_data", None))
        self.assertEqual(_day_status(10, 10), ("up", 100.0))
        self.assertEqual(_day_status(0, 4), ("down", 0.0))
        self.assertEqual(_day_status(3, 4), ("partial", 75.0))

    def test_fill_history_marks_missing_days_no_data(self) -> None:
        today = date(2026, 7, 20)
        history = _fill_uptime_history(
            {today: (8, 8), today.replace(day=19): (2, 4)},
            days=3,
            today=today,
        )
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["date"], "2026-07-18")
        self.assertEqual(history[0]["status"], "no_data")
        self.assertIsNone(history[0]["uptime"])
        self.assertEqual(history[1]["status"], "partial")
        self.assertEqual(history[1]["uptime"], 50.0)
        self.assertEqual(history[2]["status"], "up")
        self.assertEqual(history[2]["uptime"], 100.0)

    def test_uptime_from_history_ignores_no_data(self) -> None:
        history = _fill_uptime_history(
            {date(2026, 7, 20): (10, 10), date(2026, 7, 19): (0, 2)},
            days=3,
            today=date(2026, 7, 20),
        )
        self.assertEqual(_uptime_from_history(history), 50.0)

    def test_uptime_from_history_all_missing_is_none(self) -> None:
        history = _fill_uptime_history({}, days=5, today=date(2026, 7, 20))
        self.assertIsNone(_uptime_from_history(history))

    def test_merge_day_stats_filters_service(self) -> None:
        rows = [
            {"service_id": "a", "day": date(2026, 7, 20), "active": 2, "total": 2},
            {"service_id": "b", "day": date(2026, 7, 20), "active": 0, "total": 3},
            {"service_id": "a", "day": date(2026, 7, 19), "active": 1, "total": 1},
        ]
        merged = _merge_day_stats(rows, service_id="a")
        self.assertEqual(merged[date(2026, 7, 20)], (2, 2))
        self.assertEqual(merged[date(2026, 7, 19)], (1, 1))
        page_merged = _merge_day_stats(rows)
        self.assertEqual(page_merged[date(2026, 7, 20)], (2, 5))

    def test_resolve_probe_url_from_description(self) -> None:
        self.assertEqual(
            _resolve_probe_url(None, "https://example.com/health"),
            "https://example.com/health",
        )
        self.assertEqual(
            _resolve_probe_url("https://probe.example", "not-a-url"),
            "https://probe.example",
        )
        self.assertIsNone(_resolve_probe_url(None, "Primary API"))


class TestStatusTelemetryTruthfulness(unittest.IsolatedAsyncioTestCase):
    async def test_unprobed_service_does_not_inherit_healthy_page_metrics(self) -> None:
        today = datetime.now(UTC).date()
        probe_rows = [
            {
                "service_id": "healthy-service",
                "day": today,
                "active": 10,
                "total": 10,
                "p99_ms": 5.0,
            }
        ]
        with (
            patch.object(
                status_svc,
                "_probe_day_rollups",
                new=AsyncMock(return_value=probe_rows),
            ),
            patch.object(
                status_svc,
                "_analytics_kpis_24h",
                new=AsyncMock(return_value={"total_requests": 100, "p99_latency": 99.0}),
            ),
        ):
            telemetry = await status_svc._public_page_telemetry(
                MagicMock(),
                tenant_id="11111111-1111-1111-1111-111111111111",
                service_ids=["healthy-service", "unprobed-service"],
            )

        self.assertEqual(telemetry["overall_uptime"], 100.0)
        self.assertEqual(telemetry["service_sla"]["healthy-service"], 100.0)
        self.assertIsNone(telemetry["service_sla"]["unprobed-service"])
        self.assertIsNone(telemetry["service_latency"]["unprobed-service"])
        self.assertTrue(
            all(
                point["status"] == "no_data"
                for point in telemetry["service_history"]["unprobed-service"]
            )
        )

    async def test_public_intelligence_uses_norse_and_classical_families_only(self) -> None:
        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[{"threats_detected": 2, "error_rate_percent": 0.0}])
        temporal = {
            "spiking_temporal_forecast": 37.5,
            "temporal_status": "ready",
            "temporal_backend": "norse_lif",
            "temporal_sample_count": 48,
            "temporal_scored_at": "2026-07-23T12:00:00+00:00",
            "uses_norse": True,
        }
        classical = [
            {"score": 0.8, "is_anomaly": True},
            {"score": 0.2, "is_anomaly": False},
        ]
        with (
            patch(
                "app.services.ml.store.latest_temporal_signal",
                new=AsyncMock(return_value=temporal),
            ) as latest,
            patch(
                "app.services.ml.store.list_recent_scores",
                new=AsyncMock(return_value=classical),
            ) as scores,
        ):
            intelligence = await status_svc._public_page_intelligence(
                pool,
                tenant_id="11111111-1111-1111-1111-111111111111",
            )

        self.assertEqual(intelligence["spiking_temporal_forecast"], 37.5)
        self.assertEqual(intelligence["temporal_backend"], "norse_lif")
        self.assertTrue(intelligence["uses_norse"])
        self.assertEqual(intelligence["threat_anomaly_score"], 0.8)
        self.assertEqual(intelligence["threat_suspicious_ratio"], 0.5)
        self.assertEqual(intelligence["threats_detected_24h"], 2)
        self.assertEqual(
            str(latest.await_args.kwargs["tenant_id"]),
            "11111111-1111-1111-1111-111111111111",
        )
        self.assertEqual(scores.await_args.kwargs["family"], "classical_anomaly")


if __name__ == "__main__":
    unittest.main()
