"""Production OpenAPI shells are off unless ENABLE_API_DOCS is set."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class TestApiDocsGate(unittest.TestCase):
    def test_production_defaults_disable_api_docs(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "DEBUG": "true",
                # Production CORS must include an https origin (ADR-0016).
                "CORS_ORIGINS": '["https://forjd.co"]',
            },
            clear=False,
        ):
            # Drop cached settings module state for a clean Settings() load.
            import importlib

            import app.core.config as config_mod

            importlib.reload(config_mod)
            self.assertFalse(config_mod.settings.ENABLE_API_DOCS)
            self.assertFalse(config_mod.settings.DEBUG)

    def test_explicit_enable_survives_production(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "DEBUG": "false",
                "ENABLE_API_DOCS": "true",
                "CORS_ORIGINS": '["https://forjd.co"]',
            },
            clear=False,
        ):
            import importlib

            import app.core.config as config_mod

            importlib.reload(config_mod)
            self.assertTrue(config_mod.settings.ENABLE_API_DOCS)

    def tearDown(self) -> None:
        import importlib

        import app.core.config as config_mod

        importlib.reload(config_mod)


if __name__ == "__main__":
    unittest.main()
