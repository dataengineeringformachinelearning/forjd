"""Client-safe error mapping for production responses."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.http_errors import (
    GENERIC_REQUEST_FAILED,
    client_safe_detail,
    expose_error_details,
    intentional_detail,
)


class TestHttpErrors(unittest.TestCase):
    def test_intentional_detail_passes_authored_message(self) -> None:
        self.assertEqual(
            intentional_detail(ValueError("nonce reuse rejected for this key_id")),
            "nonce reuse rejected for this key_id",
        )

    def test_intentional_detail_fallback_when_empty(self) -> None:
        self.assertEqual(intentional_detail(ValueError("")), "invalid request")

    def test_client_safe_detail_hides_internals_in_production(self) -> None:
        with patch("app.core.http_errors.settings") as mock_settings:
            mock_settings.DEBUG = False
            mock_settings.is_production = True
            self.assertFalse(expose_error_details())
            self.assertEqual(
                client_safe_detail(RuntimeError("secret stack"), fallback=GENERIC_REQUEST_FAILED),
                GENERIC_REQUEST_FAILED,
            )

    def test_client_safe_detail_exposes_in_local_debug(self) -> None:
        with patch("app.core.http_errors.settings") as mock_settings:
            mock_settings.DEBUG = True
            mock_settings.is_production = False
            self.assertTrue(expose_error_details())
            self.assertEqual(
                client_safe_detail(RuntimeError("local detail")),
                "local detail",
            )


if __name__ == "__main__":
    unittest.main()
