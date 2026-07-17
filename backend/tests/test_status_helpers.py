"""Unit tests for status page overall aggregation."""

from __future__ import annotations

import unittest

from app.services.status import _overall_status


class TestOverallStatus(unittest.TestCase):
    def test_empty_operational(self) -> None:
        self.assertEqual(_overall_status([]), "operational")

    def test_worst_wins(self) -> None:
        self.assertEqual(
            _overall_status(["operational", "degraded", "major_outage"]),
            "major_outage",
        )


if __name__ == "__main__":
    unittest.main()
