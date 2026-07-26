"""Secure cookie builder defaults (ADR-0016)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.cookies import build_set_cookie


class CookieBuilderTests(unittest.TestCase):
    def test_defaults_include_httponly_samesite(self) -> None:
        with patch("app.core.cookies.settings") as mock_settings:
            mock_settings.is_production = False
            header = build_set_cookie("pref", "dark", secure=False)
        self.assertIn("pref=dark", header)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)
        self.assertIn("Path=/", header)
        self.assertNotIn("Secure", header)

    def test_production_requires_secure(self) -> None:
        with patch("app.core.cookies.settings") as mock_settings:
            mock_settings.is_production = True
            header = build_set_cookie("pref", "dark")
            self.assertIn("Secure", header)
            with self.assertRaises(ValueError):
                build_set_cookie("pref", "dark", secure=False)

    def test_samesite_none_requires_secure(self) -> None:
        with patch("app.core.cookies.settings") as mock_settings:
            mock_settings.is_production = False
            with self.assertRaises(ValueError):
                build_set_cookie("x", "y", secure=False, samesite="None")


if __name__ == "__main__":
    unittest.main()
