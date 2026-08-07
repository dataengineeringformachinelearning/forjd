"""Public API splash HTML shell."""

from __future__ import annotations

import unittest

from app.core.landing_page import render_landing

COMMUNITY = "https://dataengineeringformachinelearning.com/"
DOCS = "https://dataengineeringformachinelearning.com/documentation"


class TestLandingPage(unittest.TestCase):
    def test_landing_is_centered_brand_splash(self) -> None:
        html = render_landing()
        self.assertIn("FORJD", html)
        self.assertIn("/static/forjd.svg", html)
        self.assertIn(COMMUNITY, html)
        self.assertIn(DOCS, html)
        self.assertIn('property="og:title"', html)
        self.assertIn('rel="canonical"', html)
        self.assertIn("application/ld+json", html)
        self.assertIn("/static/geist.css", html)
        self.assertIn("/static/deml-ui.css", html)
        self.assertIn("/static/forjd-backend.css", html)
        self.assertIn("forjd-backend-shell", html)
        self.assertIn("forjd-backend-logo", html)
        self.assertIn("forjd-backend-splash", html)
        self.assertNotIn("forjd-backend-nav", html)
        self.assertNotIn("site-footer", html)
        self.assertNotIn("forjd-backend-caption", html)
        self.assertNotIn("banner banner--hero", html)
        self.assertNotIn('href="/docs"', html)
        self.assertNotIn('href="/redoc"', html)
        self.assertNotIn("swagger-ui", html)
        self.assertNotIn("https://forjd.co/", html)
        self.assertNotIn("suite-tokens", html)
        self.assertNotIn("<style>", html)


if __name__ == "__main__":
    unittest.main()
