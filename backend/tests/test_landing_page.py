"""Public API splash + docs HTML shells."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.core.docs_page import render_docs
from app.core.landing_page import render_landing
from app.core.redoc_page import render_redoc

COMMUNITY = "https://dataengineeringformachinelearning.com/"


class TestLandingPage(unittest.TestCase):
    def test_landing_is_minimal_logo_splash(self) -> None:
        html = render_landing()
        self.assertIn("FORJD", html)
        self.assertIn("/static/forjd.svg", html)
        self.assertIn(COMMUNITY, html)
        self.assertIn("/static/deml-ui.css", html)
        self.assertIn("/static/forjd-backend.css", html)
        self.assertIn("forjd-backend-shell", html)
        self.assertIn("forjd-backend-logo", html)
        self.assertNotIn("swagger-ui", html)
        self.assertNotIn("https://forjd.co/", html)
        self.assertNotIn("suite-tokens", html)
        self.assertNotIn("<style>", html)

    def test_docs_shell_uses_deml_ui(self) -> None:
        html = render_docs()
        self.assertIn("swagger-ui", html)
        self.assertIn("/static/deml-ui.css", html)
        self.assertIn("/static/forjd-backend.css", html)
        self.assertIn("/static/vendor/swagger-ui-dist/swagger-ui-bundle.js", html)
        self.assertIn("/static/docs-swagger-init.js", html)
        self.assertIn("forjd-backend-topbar", html)
        self.assertNotIn("#00b4ff", html)
        self.assertNotIn("#2176ff", html)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertNotIn("<style>", html)
        self.assertIn(COMMUNITY, html)
        self.assertNotIn("https://forjd.co/", html)
        self.assertIn('href="/redoc"', html)
        self.assertIn('<main aria-label="FORJD interactive API documentation">', html)

    def test_redoc_shell_uses_deml_ui(self) -> None:
        html = render_redoc(nonce="test-nonce")
        self.assertIn("redoc", html)
        self.assertIn("/static/deml-ui.css", html)
        self.assertIn("/static/forjd-backend.css", html)
        self.assertIn("/static/vendor/redoc/redoc.standalone.js", html)
        self.assertIn("/static/redoc-init.js", html)
        self.assertIn("forjd-backend-topbar", html)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertNotIn("<style>", html)
        self.assertIn(COMMUNITY, html)
        self.assertNotIn("https://forjd.co/", html)
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
