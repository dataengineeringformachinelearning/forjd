"""Unit tests for CES / percentile analytics formulas."""

from __future__ import annotations

import unittest

from app.services.analytics import ces_composite, percentile_index, uptime_status


class TestAnalyticsFormulas(unittest.TestCase):
    def test_percentile_index(self) -> None:
        self.assertEqual(percentile_index(100, 0.99), 98)
        self.assertEqual(percentile_index(0), 0)

    def test_uptime_status(self) -> None:
        self.assertEqual(uptime_status(1.0), "operational")
        self.assertEqual(uptime_status(0.96), "partial_outage")
        self.assertEqual(uptime_status(0.5), "major_outage")

    def test_ces_composite_bounds(self) -> None:
        out = ces_composite(uptime_pct=99.0, incidents=1, p99_ms=200.0)
        self.assertGreaterEqual(out["ces_level"], 0.0)
        self.assertLessEqual(out["ces_level"], 100.0)


if __name__ == "__main__":
    unittest.main()
