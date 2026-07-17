"""User-agent parsing tests."""

from __future__ import annotations

import unittest

from app.core.enrichment import parse_user_agent


class TestUserAgent(unittest.TestCase):
    def test_chrome_desktop(self) -> None:
        ua = parse_user_agent(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.assertEqual(ua["browser_name"], "Chrome")
        self.assertFalse(ua["is_bot"])

    def test_bot(self) -> None:
        ua = parse_user_agent("Googlebot/2.1")
        self.assertTrue(ua["is_bot"])
        self.assertEqual(ua["device_type"], "Bot")


if __name__ == "__main__":
    unittest.main()
