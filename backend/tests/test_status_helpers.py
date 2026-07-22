"""Unit tests for status page helpers."""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from typing import Any

from app.services.status import (
    _day_status,
    _fill_uptime_history,
    _merge_day_stats,
    _overall_status,
    _page_dict,
    _public_page_dict,
    _resolve_probe_url,
    _uptime_from_history,
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


if __name__ == "__main__":
    unittest.main()
