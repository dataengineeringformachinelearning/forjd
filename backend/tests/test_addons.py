"""Unit tests for the FORJD add-on registry and enablement gate."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.addons import ADDONS, HookPoint, addon_enabled, enabled_addons, get_addon
from app.addons.clients import AddonDisabled, osv_query
from app.addons.hooks import clear_hooks, register_hook, run_hooks, run_hooks_task

EXPECTED_SLUGS = {
    "osv-dev",
    "osv-scanner",
    "osv-scalibr",
    "nuclei",
    "honeydb",
    "go-cve-dictionary",
    "jax",
    "acme",
    "robotframework",
    "oss-fuzz",
    "design-patterns-python",
}


class TestAddonCatalog(unittest.TestCase):
    def test_catalog_covers_all_requested_libraries(self) -> None:
        self.assertEqual({a.slug for a in ADDONS}, EXPECTED_SLUGS)

    def test_slugs_are_unique(self) -> None:
        slugs = [a.slug for a in ADDONS]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_every_addon_has_source_url(self) -> None:
        for a in ADDONS:
            self.assertTrue(a.source_url.startswith("https://github.com/"), a.slug)


class TestEnablementGate(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        with patch("app.addons.registry.settings") as s:
            s.ADDONS_ENABLED = []
            s.FORJD_ADDONS_CONFIG = ""
            self.assertEqual(enabled_addons(), ())
            self.assertFalse(addon_enabled("osv-dev"))

    def test_explicit_enable_subset(self) -> None:
        with patch("app.addons.registry.settings") as s:
            s.ADDONS_ENABLED = ["osv-dev", "nuclei"]
            s.FORJD_ADDONS_CONFIG = ""
            enabled = {a.slug for a in enabled_addons()}
            self.assertEqual(enabled, {"osv-dev", "nuclei"})
            self.assertTrue(addon_enabled("osv-dev"))
            self.assertFalse(addon_enabled("honeydb"))

    def test_all_enables_full_catalog(self) -> None:
        with patch("app.addons.registry.settings") as s:
            s.ADDONS_ENABLED = ["all"]
            s.FORJD_ADDONS_CONFIG = ""
            self.assertEqual(len(enabled_addons()), len(ADDONS))

    def test_unknown_slug_ignored(self) -> None:
        with patch("app.addons.registry.settings") as s:
            s.ADDONS_ENABLED = ["not-a-real-addon"]
            s.FORJD_ADDONS_CONFIG = ""
            self.assertEqual(enabled_addons(), ())

    def test_yaml_config_enables_subset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "addons.yaml"
            path.write_text("addons:\n  enabled: [jax, nuclei]\n", encoding="utf-8")
            with patch("app.addons.registry.settings") as s:
                s.ADDONS_ENABLED = []
                s.FORJD_ADDONS_CONFIG = str(path)
                self.assertEqual({a.slug for a in enabled_addons()}, {"jax", "nuclei"})

    def test_deml_yaml_enables_full_catalog(self) -> None:
        path = Path(__file__).resolve().parents[1] / "config" / "addons" / "deml.yaml"
        with patch("app.addons.registry.settings") as s:
            s.ADDONS_ENABLED = []
            s.FORJD_ADDONS_CONFIG = str(path)
            self.assertEqual(len(enabled_addons()), len(ADDONS))

    def test_env_takes_precedence_over_yaml(self) -> None:
        with patch("app.addons.registry.settings") as s:
            s.ADDONS_ENABLED = ["osv-dev"]
            s.FORJD_ADDONS_CONFIG = "/does/not/need/to/exist.yaml"
            self.assertEqual({a.slug for a in enabled_addons()}, {"osv-dev"})


class TestAddonClientsGate(unittest.TestCase):
    def test_disabled_client_raises(self) -> None:
        with patch("app.addons.registry.settings") as s:
            s.ADDONS_ENABLED = []
            s.FORJD_ADDONS_CONFIG = ""
            with self.assertRaises(AddonDisabled):
                asyncio.run(osv_query(name="requests", version="2.0.0"))

    def test_get_addon_roundtrip(self) -> None:
        addon = get_addon("osv-dev")
        self.assertIsNotNone(addon)
        assert addon is not None
        self.assertEqual(addon.name, "OSV.dev")


class TestAddonHooks(unittest.TestCase):
    def tearDown(self) -> None:
        clear_hooks()

    def test_only_enabled_hooks_execute(self) -> None:
        register_hook("jax", HookPoint.AFTER_WORKFLOW, lambda ctx: {"seen": ctx["value"]})
        register_hook("nuclei", HookPoint.AFTER_WORKFLOW, lambda _ctx: {"ran": True})
        with patch("app.addons.registry.settings") as s:
            s.ADDONS_ENABLED = ["jax"]
            results = run_hooks(HookPoint.AFTER_WORKFLOW, {"value": 7})
        self.assertEqual(results, [{"addon": "jax", "ok": True, "result": {"seen": 7}}])

    def test_hook_failure_is_isolated(self) -> None:
        def fail(_context: object) -> None:
            raise RuntimeError("optional service unavailable")

        register_hook("osv-dev", HookPoint.BEFORE_WORKFLOW, fail)
        with patch("app.addons.registry.settings") as s:
            s.ADDONS_ENABLED = ["osv-dev"]
            results = run_hooks_task.fn(HookPoint.BEFORE_WORKFLOW.value, {})
        self.assertFalse(results[0]["ok"])
        self.assertIn("unavailable", results[0]["error"])

    def test_unknown_addon_cannot_register(self) -> None:
        with self.assertRaises(ValueError):
            register_hook("unknown", HookPoint.AFTER_WORKFLOW, lambda _ctx: None)


if __name__ == "__main__":
    unittest.main()
