"""Security response headers (XSS hardening; CSRF is header-auth, not tokens)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from app.core.security import SecurityHeadersMiddleware


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 123),
            "server": ("test", 443),
        }
    )


class TestSecurityHeadersMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_sets_csp_and_browser_hardening_headers(self) -> None:
        async def call_next(_request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        middleware = SecurityHeadersMiddleware(AsyncMock())
        response = await middleware.dispatch(_request("/health"), call_next)

        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertIn("geolocation=()", response.headers["Permissions-Policy"])
        self.assertEqual(
            response.headers["Content-Security-Policy"],
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        self.assertEqual(response.headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(response.headers["Cross-Origin-Resource-Policy"], "same-site")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_html_shells_get_docs_csp(self) -> None:
        async def call_next(_request: Request) -> HTMLResponse:
            return HTMLResponse("<html></html>")

        middleware = SecurityHeadersMiddleware(AsyncMock())
        for path in ("/", "/docs", "/redoc"):
            response = await middleware.dispatch(_request(path), call_next)
            csp = response.headers["Content-Security-Policy"]
            self.assertIn("cdn.jsdelivr.net", csp)
            self.assertIn("style-src", csp)
            self.assertIn("script-src", csp)
            self.assertIn("connect-src 'self'", csp)


if __name__ == "__main__":
    unittest.main()
