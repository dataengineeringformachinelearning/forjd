"""Public API landing + docs HTML shells."""

from __future__ import annotations

import unittest

from app.core.docs_page import render_docs
from app.core.landing_page import render_landing


class TestLandingPage(unittest.TestCase):
    def test_landing_has_brand_purpose_and_probe_links(self) -> None:
        html = render_landing()
        self.assertIn("FORJD", html)
        self.assertIn("Universal secure streaming engine", html)
        self.assertIn('href="/docs"', html)
        self.assertIn('href="/health"', html)
        self.assertIn('href="/ready"', html)
        self.assertIn('href="/openapi.json"', html)
        self.assertIn("--fj-primary", html)
        self.assertNotIn("swagger-ui", html)

    def test_docs_shell_keeps_fjord_theme(self) -> None:
        html = render_docs()
        self.assertIn("swagger-ui", html)
        self.assertIn("--fj-primary", html)
        self.assertIn('href="/"', html)


if __name__ == "__main__":
    unittest.main()
