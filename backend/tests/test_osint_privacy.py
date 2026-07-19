"""HIBP / OSINT privacy helpers — no raw email persistence."""

from __future__ import annotations

import unittest

from app.services.osint import _email_location_digest


class OsintPrivacyTests(unittest.TestCase):
    def test_email_digest_is_stable_and_case_insensitive(self) -> None:
        a = _email_location_digest("User@Example.COM")
        b = _email_location_digest("user@example.com")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("sha256:"))
        self.assertNotIn("@", a)
        self.assertNotIn("user", a.lower())


if __name__ == "__main__":
    unittest.main()
