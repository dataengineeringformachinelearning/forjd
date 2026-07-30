"""Public API splash + docs HTML shells."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.core.docs_page import render_docs
from app.core.landing_page import render_landing
from app.core.redoc_page import render_redoc


class TestLandingPage(unittest.TestCase):
    def test_landing_is_minimal_logo_splash(self) -> None:
        html = render_landing()
        self.assertIn("FORJD", html)
        self.assertIn("/static/forjd.svg", html)
        self.assertIn("https://forjd.co/", html)
        self.assertIn("/static/suite-tokens.css", html)
        self.assertIn("/static/suite-components.css", html)
        self.assertIn("/static/suite-backend.css", html)
        self.assertIn("suite-backend-shell", html)
        self.assertIn("suite-backend-logo", html)
        self.assertNotIn("swagger-ui", html)
        self.assertNotIn("Universal secure streaming engine", html)
        self.assertNotIn("<style>", html)

    def test_docs_shell_keeps_fjord_theme(self) -> None:
        html = render_docs()
        self.assertIn("swagger-ui", html)
        self.assertIn("/static/suite-tokens.css", html)
        self.assertIn("/static/suite-components.css", html)
        self.assertIn("/static/suite-backend.css", html)
        self.assertIn("/static/suite-apidocs.css", html)
        self.assertIn("/static/forjd-apidocs.css", html)
        self.assertIn("/static/vendor/swagger-ui-dist/swagger-ui-bundle.js", html)
        self.assertIn("/static/docs-swagger-init.js", html)
        self.assertIn("suite-backend-topbar", html)
        self.assertNotIn("#00b4ff", html)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertNotIn("<style>", html)
        self.assertIn("https://forjd.co/", html)
        self.assertIn('href="/redoc"', html)
        self.assertIn('<main aria-label="FORJD interactive API documentation">', html)
        self.assertIn("forjd interactive API documentation</h1>", html)

    def test_redoc_shell_keeps_fjord_theme(self) -> None:
        html = render_redoc(nonce="test-nonce")
        self.assertIn("redoc", html)
        self.assertIn("/static/suite-tokens.css", html)
        self.assertIn("/static/suite-components.css", html)
        self.assertIn("/static/suite-backend.css", html)
        self.assertIn("/static/suite-apidocs.css", html)
        self.assertIn("/static/forjd-apidocs.css", html)
        self.assertIn("/static/vendor/redoc/redoc.standalone.js", html)
        self.assertIn("/static/redoc-init.js", html)
        self.assertIn("suite-backend-topbar", html)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertNotIn("<style>", html)
        self.assertIn("https://forjd.co/", html)
        self.assertIn('href="/docs"', html)
        self.assertIn('data-csp-nonce="test-nonce"', html)
        self.assertIn('data-openapi-url="/openapi.json"', html)
        self.assertIn('<main id="redoc-container" aria-label="FORJD API reference">', html)

    def test_redoc_normalizes_navigation_and_search_result_menus(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "static" / "redoc-init.js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            '.menu-content ul, .menu-content [data-role="search:results"]',
            script,
        )


if __name__ == "__main__":
    unittest.main()
