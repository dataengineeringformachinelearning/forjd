"""SSRF-safe site URL validation tests."""

from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from app.services.site_url import (
    normalize_technology_name,
    normalize_version,
    validate_public_http_url,
)


class TestSiteUrlHelpers(unittest.TestCase):
    def test_normalize_technology_name(self) -> None:
        self.assertEqual(normalize_technology_name("  Next.js  "), "next.js")

    def test_normalize_version(self) -> None:
        self.assertEqual(normalize_version("1.2.3"), "1.2.3")
        self.assertEqual(normalize_version("latest"), "")

    def test_validate_public_http_url_rejects_private_targets(self) -> None:
        with self.assertRaises(ValueError):
            validate_public_http_url("http://example.com", require_https=True)
        with self.assertRaises(ValueError):
            validate_public_http_url("https://127.0.0.1/", require_https=True)
        with self.assertRaises(ValueError):
            validate_public_http_url("https://user:pass@example.com/", require_https=True)

    def test_validate_public_http_url_accepts_public_https(self) -> None:
        fake = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
        ]
        with patch("app.services.site_url.socket.getaddrinfo", return_value=fake):
            self.assertEqual(
                validate_public_http_url("https://example.com/path", require_https=True),
                "https://example.com/path",
            )


if __name__ == "__main__":
    unittest.main()
