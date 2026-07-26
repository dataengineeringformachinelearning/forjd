"""Feature-flag projection over Settings."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.core.feature_flags import resolve_feature_flags


class TestFeatureFlags(unittest.TestCase):
    def test_addons_all_and_slug_lookup(self) -> None:
        cfg = MagicMock()
        cfg.FORJD_ADDONS = "all"
        cfg.ADDONS_ENABLED = ["all"]
        cfg.ENABLE_API_DOCS = True
        cfg.RATE_LIMIT_ENABLED = True
        cfg.SOFT_MIGRATE_SCHEMA = False
        cfg.REQUIRE_RLS = True
        cfg.REQUIRE_CRYPTO_SESSION = True
        cfg.SUPABASE_AUTH_REQUIRED = True
        cfg.ANALYTICS_ROLLUP_INTERVAL_SECONDS = 300.0
        cfg.TRAINING_TICK_SECONDS = 0.0
        cfg.RETENTION_SWEEP_INTERVAL_SECONDS = 3600.0
        cfg.PROJECTION_TICK_SECONDS = 0.0

        flags = resolve_feature_flags(cfg)
        self.assertTrue(flags.addons_all)
        self.assertTrue(flags.addon_enabled("osv-dev"))
        self.assertTrue(flags.analytics_worker_enabled)
        self.assertFalse(flags.training_worker_enabled)
        self.assertTrue(flags.retention_worker_enabled)
        self.assertFalse(flags.projection_tick_enabled)

    def test_addons_subset(self) -> None:
        cfg = MagicMock()
        cfg.FORJD_ADDONS = "osv-dev,nuclei"
        cfg.ADDONS_ENABLED = ["osv-dev", "nuclei"]
        cfg.ENABLE_API_DOCS = False
        cfg.RATE_LIMIT_ENABLED = False
        cfg.SOFT_MIGRATE_SCHEMA = True
        cfg.REQUIRE_RLS = False
        cfg.REQUIRE_CRYPTO_SESSION = False
        cfg.SUPABASE_AUTH_REQUIRED = False
        cfg.ANALYTICS_ROLLUP_INTERVAL_SECONDS = 0.0
        cfg.TRAINING_TICK_SECONDS = 0.0
        cfg.RETENTION_SWEEP_INTERVAL_SECONDS = 0.0
        cfg.PROJECTION_TICK_SECONDS = 0.0

        flags = resolve_feature_flags(cfg)
        self.assertFalse(flags.addons_all)
        self.assertTrue(flags.addon_enabled("nuclei"))
        self.assertFalse(flags.addon_enabled("honeydb"))
        self.assertFalse(flags.rate_limit_enabled)


if __name__ == "__main__":
    unittest.main()
