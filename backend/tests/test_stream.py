"""Unit tests for sealed-metadata rollups and anomaly flags."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import engine as engine_svc
from app.services.stream import pathway_sealed_process
from app.workflows.models import WorkflowDefinition


# --- Metadata anomaly (E2EE-safe; never needs ciphertext) ---
class TestSealedStreamProcess(unittest.TestCase):
    def test_empty(self) -> None:
        out = pathway_sealed_process([])
        self.assertTrue(out["ok"])
        self.assertEqual(out["count"], 0)
        self.assertEqual(out["results"], [])

    def test_engine_outage_uses_successful_python_fallback(self) -> None:
        events = [
            {"event_id": "a", "tenant_id": "tenant-a", "cipher_len": 10},
            {"event_id": "b", "tenant_id": "tenant-a", "cipher_len": 30},
            {"event_id": "c", "tenant_id": "tenant-b", "cipher_len": 5},
        ]

        with patch(
            "app.services.stream.engine_svc.run_sealed_pipeline_sync",
            return_value=None,
        ):
            out = pathway_sealed_process(events)

        self.assertTrue(out["ok"])
        self.assertEqual(out["engine"], "python-fallback")
        self.assertEqual(out["count"], 3)
        self.assertEqual(out["tenants"], 2)
        self.assertEqual(
            out["by_tenant"],
            {
                "tenant-a": {"count": 2, "bytes": 40, "max_cipher_len": 30},
                "tenant-b": {"count": 1, "bytes": 5, "max_cipher_len": 5},
            },
        )
        self.assertTrue(all(row["engine"] == "python-fallback" for row in out["results"]))

    def test_rust_pyo3_pipeline_contract(self) -> None:
        out = engine_svc.run_sealed_pipeline_sync(
            [{"event_id": "e", "tenant_id": "tenant", "cipher_len": 12}],
            steps=["rollup"],
            projection_name="sealed.test",
            workflow_id="test",
        )

        self.assertIsNotNone(out)
        assert out is not None
        self.assertTrue(out["ok"])
        self.assertEqual(out["engine"], "forjd-engine")
        self.assertEqual(out["by_tenant"]["tenant"]["bytes"], 12)

    def test_rollup_and_outlier(self) -> None:
        tid = "11111111-1111-1111-1111-111111111111"
        events = [
            {"event_id": f"e{i}", "tenant_id": tid, "key_id": "k1", "cipher_len": 100}
            for i in range(8)
        ]
        events.append(
            {
                "event_id": "e-big",
                "tenant_id": tid,
                "key_id": "k1",
                "cipher_len": 50_000,
            }
        )
        wf = WorkflowDefinition(
            id="test_anom",
            name="Test",
            pipeline={
                "processor": "sealed_metadata",
                "steps": ["rollup", "size_anomaly"],
                "size_anomaly": {"zscore": 2.0, "max_cipher_len": 262144},
            },
            outputs={"tags": {"use_case": "test"}},
        )
        out = pathway_sealed_process(events, workflow=wf)
        self.assertTrue(out["ok"])
        self.assertEqual(out["count"], 9)
        self.assertGreaterEqual(out["anomaly_count"], 1)
        flagged = [a for a in out["anomalies"] if a["event_id"] == "e-big"]
        self.assertEqual(len(flagged), 1)
        self.assertTrue(flagged[0]["is_anomaly"])
        self.assertTrue(
            any(r.get("metadata", {}).get("use_case") == "test" for r in out["results"])
        )

    def test_rollup_only_skips_anomaly(self) -> None:
        tid = "22222222-2222-2222-2222-222222222222"
        wf = WorkflowDefinition(
            id="rollup_only",
            name="Rollup",
            pipeline={"processor": "sealed_metadata", "steps": ["rollup"]},
        )
        out = pathway_sealed_process(
            [
                {
                    "event_id": "huge",
                    "tenant_id": tid,
                    "key_id": "k",
                    "cipher_len": 300_000,
                }
            ],
            workflow=wf,
        )
        self.assertEqual(out["anomaly_count"], 0)
        self.assertTrue(all(r["kind"] == "rollup" for r in out["results"]))

    def test_hard_max_cipher_len(self) -> None:
        tid = "33333333-3333-3333-3333-333333333333"
        wf = WorkflowDefinition(
            id="hard_max",
            name="Hard",
            pipeline={
                "steps": ["size_anomaly"],
                "size_anomaly": {"zscore": 99.0, "max_cipher_len": 1000},
            },
        )
        out = pathway_sealed_process(
            [
                {
                    "event_id": "huge",
                    "tenant_id": tid,
                    "key_id": "k",
                    "cipher_len": 300_000,
                }
            ],
            workflow=wf,
        )
        self.assertGreaterEqual(out["anomaly_count"], 1)
        self.assertEqual(out["anomalies"][0]["reason"], "max_cipher_len")


if __name__ == "__main__":
    unittest.main()
