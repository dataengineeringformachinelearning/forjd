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

        default = resolve_workflow(content_type="application/forjd-event+v1")
        self.assertEqual(default.id, "default_sealed")

        # content_type-only still hits the generic telemetry example
        threat = resolve_workflow(content_type="application/forjd-telemetry+v1")
        self.assertEqual(threat.id, "threat_telemetry")

        analytics = resolve_workflow(content_type="application/forjd-analytics+v1")
        self.assertEqual(analytics.id, "analytics_events")

    def test_explicit_workflow_id(self) -> None:
        wf = resolve_workflow(
            content_type="application/forjd-event+v1",
            workflow_id="analytics_events",
        )
        self.assertEqual(wf.id, "analytics_events")

    def test_partner_workflow_id_alias(self) -> None:
        """YAML aliases map partner wire ids → canonical family (config only)."""
        from app.workflows import registry as wf_registry
        from app.workflows.registry import canonical_event_type, canonical_workflow_id

        text = """
id: universal_family
name: Universal family
enabled: true
match:
  content_types: [application/forjd-partner+v1]
aliases:
  workflow_ids: [partner_telemetry]
  event_types:
    threat.metric: [partner.metric]
    threat.alert: [partner.alert]
pipeline:
  processor: sealed_metadata
  steps: [rollup]
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "universal_family.yaml"
            path.write_text(text, encoding="utf-8")
            clear_cache()
            # Point registry at the temp dir for this test only.
            original = wf_registry.workflows_dir
            wf_registry.workflows_dir = lambda: Path(tmp)  # type: ignore[method-assign]
            try:
                wf = resolve_workflow(
                    content_type="application/forjd-partner+v1",
                    workflow_id="partner_telemetry",
                )
                self.assertEqual(wf.id, "universal_family")
                self.assertEqual(
                    canonical_workflow_id("partner_telemetry"),
                    "universal_family",
                )
                self.assertEqual(canonical_event_type("partner.metric"), "threat.metric")
                self.assertEqual(canonical_event_type("partner.alert"), "threat.alert")
            finally:
                wf_registry.workflows_dir = original  # type: ignore[method-assign]
                clear_cache()

    def test_yaml_aliases_roundtrip(self) -> None:
        text = """
id: partner_family
name: Partner family
match:
  content_types: [application/forjd-partner+v1]
aliases:
  workflow_ids: [partner_alias_wf]
  event_types:
    partner.metric: [alias.metric]
  content_types: [application/vnd.partner.alias+v1]
pipeline:
  processor: sealed_metadata
  steps: [rollup]
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "partner.yaml"
            path.write_text(text, encoding="utf-8")
            loaded = load_workflow_file(path)
        self.assertEqual(loaded.aliases.workflow_ids, ["partner_alias_wf"])
        self.assertEqual(loaded.aliases.event_types["partner.metric"], ["alias.metric"])
        self.assertEqual(loaded.aliases.content_types, ["application/vnd.partner.alias+v1"])

    def test_content_type_alias_resolves_workflow(self) -> None:
        """Partner MIME aliases map onto match.content_types families."""
        from app.workflows import registry as wf_registry

        text = """
id: universal_ct
name: Universal CT
enabled: true
match:
  content_types: [application/forjd-partner+v1]
aliases:
  content_types: [application/vnd.legacy.partner+v1]
pipeline:
  processor: sealed_metadata
  steps: [rollup]
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "universal_ct.yaml"
            path.write_text(text, encoding="utf-8")
            clear_cache()
            original = wf_registry.workflows_dir
            wf_registry.workflows_dir = lambda: Path(tmp)  # type: ignore[method-assign]
            try:
                wf = resolve_workflow(content_type="application/vnd.legacy.partner+v1")
                self.assertEqual(wf.id, "universal_ct")
            finally:
                wf_registry.workflows_dir = original  # type: ignore[method-assign]
                clear_cache()

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
