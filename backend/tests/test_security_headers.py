"""Security response headers (XSS hardening; CSRF is header-auth, not tokens)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.security import SecurityHeadersMiddleware


class TestSecurityHeadersMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_sets_csp_and_browser_hardening_headers(self) -> None:
        async def call_next(_request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        middleware = SecurityHeadersMiddleware(AsyncMock())
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/health",
            "raw_path": b"/health",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 123),
            "server": ("test", 443),
        }
        request = Request(scope)
        response = await middleware.dispatch(request, call_next)

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


if __name__ == "__main__":
    unittest.main()
