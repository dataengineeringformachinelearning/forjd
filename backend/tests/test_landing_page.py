"""Public API splash + docs HTML shells."""

from __future__ import annotations

import unittest

from app.core.docs_page import render_docs
from app.core.landing_page import render_landing
from app.core.redoc_page import render_redoc


class TestLandingPage(unittest.TestCase):
    def test_landing_is_minimal_logo_splash(self) -> None:
        html = render_landing()
        self.assertIn("FORJD", html)
        self.assertIn("/static/forjd.svg", html)
        self.assertIn("https://forjd.co/", html)
        self.assertIn("--fj-bg", html)
        self.assertNotIn("swagger-ui", html)
        self.assertNotIn("Universal secure streaming engine", html)

    def test_docs_shell_keeps_fjord_theme(self) -> None:
        html = render_docs()
        self.assertIn("swagger-ui", html)
        self.assertIn("--fj-primary", html)
        self.assertIn("https://forjd.co/", html)
        self.assertIn('href="/redoc"', html)
        self.assertIn("--fj-font-sans", html)

    def test_redoc_shell_keeps_fjord_theme(self) -> None:
        html = render_redoc()
        self.assertIn("redoc", html)
        self.assertIn("--fj-primary", html)
        self.assertIn("https://forjd.co/", html)
        self.assertIn('href="/docs"', html)


if __name__ == "__main__":
    unittest.main()
