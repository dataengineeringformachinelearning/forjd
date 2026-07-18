"""Unit tests for YAML workflow loader + registry resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.workflows import clear_cache, resolve_workflow
from app.workflows.loader import load_workflow_file
from app.workflows.models import WorkflowDefinition
from app.workflows.registry import all_workflows, list_workflow_summaries


# --- Loader ---
class TestWorkflowLoader(unittest.TestCase):
    def test_load_yaml_roundtrip(self) -> None:
        text = """
id: sample_wf
name: Sample
default: true
match:
  content_types: [application/forjd-event+v1]
pipeline:
  processor: sealed_metadata
  steps: [rollup]
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.yaml"
            path.write_text(text, encoding="utf-8")
            wf = load_workflow_file(path)
        self.assertEqual(wf.id, "sample_wf")
        self.assertEqual(wf.pipeline.steps, ["rollup"])


# --- Registry (uses repo workflows/ when present) ---
class TestWorkflowRegistry(unittest.TestCase):
    def setUp(self) -> None:
        clear_cache()

    def tearDown(self) -> None:
        clear_cache()

    def test_default_and_threat_resolution(self) -> None:
        workflows = all_workflows()
        ids = {w.id for w in workflows}
        self.assertIn("default_sealed", ids)
        self.assertIn("threat_telemetry", ids)
        self.assertIn("deml_telemetry", ids)

        default = resolve_workflow(content_type="application/forjd-event+v1")
        self.assertEqual(default.id, "default_sealed")

        # content_type-only still hits the generic telemetry example
        threat = resolve_workflow(content_type="application/forjd-telemetry+v1")
        self.assertEqual(threat.id, "threat_telemetry")

        deml = resolve_workflow(
            content_type="application/forjd-telemetry+v1",
            event_type="deml.metric",
        )
        self.assertEqual(deml.id, "deml_telemetry")

        analytics = resolve_workflow(content_type="application/forjd-analytics+v1")
        self.assertEqual(analytics.id, "analytics_events")

    def test_explicit_workflow_id(self) -> None:
        wf = resolve_workflow(
            content_type="application/forjd-event+v1",
            workflow_id="analytics_events",
        )
        self.assertEqual(wf.id, "analytics_events")

        deml = resolve_workflow(
            content_type="application/forjd-telemetry+v1",
            workflow_id="deml_telemetry",
        )
        self.assertEqual(deml.id, "deml_telemetry")

    def test_unknown_workflow_id(self) -> None:
        with self.assertRaises(ValueError):
            resolve_workflow(
                content_type="application/forjd-event+v1",
                workflow_id="does_not_exist",
            )

    def test_summaries(self) -> None:
        summaries = list_workflow_summaries()
        self.assertGreaterEqual(len(summaries), 1)
        self.assertTrue(all("id" in s and "processor" in s for s in summaries))

    def test_builtin_model_defaults(self) -> None:
        wf = WorkflowDefinition(id="x", name="X", default=True)
        self.assertEqual(wf.pipeline.processor, "sealed_metadata")
        self.assertIn("e2ee", wf.encryption.modes)
        self.assertEqual(wf.pipeline.projection_name, "sealed.default")
        self.assertIsNotNone(wf.pipeline.projection)
        self.assertEqual(wf.pipeline.projection.name, "sealed.default")

    def test_projection_object_syncs_name(self) -> None:
        text = """
id: proj_wf
name: Proj
match:
  content_types: [application/forjd-event+v1]
pipeline:
  processor: sealed_metadata
  steps: [rollup]
  projection:
    name: custom.proj
    version: 2
    retention_days: 30
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proj.yaml"
            path.write_text(text, encoding="utf-8")
            loaded = load_workflow_file(path)
        self.assertEqual(loaded.pipeline.projection_name, "custom.proj")
        self.assertEqual(loaded.pipeline.projection.version, 2)

    def test_extensible_steps(self) -> None:
        wf = WorkflowDefinition(
            id="ext",
            name="Ext",
            pipeline={"steps": ["rollup", "size_anomaly", "my_custom_detector"]},
        )
        self.assertIn("my_custom_detector", wf.pipeline.steps)


if __name__ == "__main__":
    unittest.main()
