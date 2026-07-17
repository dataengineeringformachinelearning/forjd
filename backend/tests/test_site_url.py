"""SSRF-safe site URL validation tests."""

from __future__ import annotations

import unittest

from app.services.site_url import normalize_technology_name, normalize_version


class TestSiteUrlHelpers(unittest.TestCase):
    def test_normalize_technology_name(self) -> None:
        self.assertEqual(normalize_technology_name("  Next.js  "), "next.js")

    def test_normalize_version(self) -> None:
        self.assertEqual(normalize_version("1.2.3"), "1.2.3")
        self.assertEqual(normalize_version("latest"), "")


if __name__ == "__main__":
    unittest.main()
