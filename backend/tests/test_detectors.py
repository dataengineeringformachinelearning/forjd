"""Unit tests for pluggable metadata anomaly detectors."""

from __future__ import annotations

import unittest

from app.workflows.detectors import REGISTRY, run_detectors
from app.workflows.detectors.rate_anomaly import detect as rate_detect
from app.workflows.detectors.size_anomaly import detect as size_detect


class TestDetectors(unittest.TestCase):
    def test_registry_has_size_and_rate(self) -> None:
        self.assertIn("size_anomaly", REGISTRY)
        self.assertIn("rate_anomaly", REGISTRY)

    def test_size_outlier(self) -> None:
        tid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        events = [
            {"event_id": f"e{i}", "tenant_id": tid, "key_id": "k", "cipher_len": 50}
            for i in range(6)
        ]
        events.append({"event_id": "big", "tenant_id": tid, "key_id": "k", "cipher_len": 40_000})
        out = size_detect(events, {"zscore": 2.0, "max_cipher_len": 100_000})
        flagged = [r for r in out if r["event_id"] == "big"]
        self.assertTrue(flagged[0]["is_anomaly"])

    def test_rate_burst(self) -> None:
        tid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        events = [
            {"event_id": f"e{i}", "tenant_id": tid, "key_id": "k", "cipher_len": 10}
            for i in range(10)
        ]
        out = rate_detect(events, {"max_events": 5})
        self.assertTrue(all(r["is_anomaly"] for r in out))

    def test_run_detectors_merges(self) -> None:
        tid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        events = [{"event_id": "1", "tenant_id": tid, "key_id": "k", "cipher_len": 300_000}]
        out = run_detectors(
            events,
            steps=["size_anomaly", "rate_anomaly"],
            params_by_step={
                "size_anomaly": {"zscore": 99, "max_cipher_len": 1000},
                "rate_anomaly": {"max_events": 100},
            },
        )
        self.assertGreaterEqual(len(out), 2)
        self.assertTrue(any(r["detector"] == "size_anomaly" and r["is_anomaly"] for r in out))


if __name__ == "__main__":
    unittest.main()
