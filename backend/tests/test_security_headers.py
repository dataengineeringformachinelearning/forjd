"""Security response headers (XSS hardening; CSRF is header-auth, not tokens)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from app.core.security import HttpsRedirectMiddleware, SecurityHeadersMiddleware


def _request(
    path: str,
    *,
    scheme: str = "https",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": scheme,
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": headers or [],
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
        pp = response.headers["Permissions-Policy"]
        self.assertIn("geolocation=()", pp)
        self.assertIn("payment=()", pp)
        self.assertIn("browsing-topics=()", pp)
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
            # Swagger/ReDoc are self-hosted — CDN must not remain a docs dependency.
            self.assertNotIn("cdn.jsdelivr.net", csp)
            self.assertIn("form-action 'self'", csp)
            self.assertIn("googletagmanager.com", csp)
            self.assertIn("clarity.ms", csp)
            self.assertIn("style-src 'self'", csp)
            self.assertIn("script-src", csp)
            self.assertIn("connect-src 'self'", csp)
            if path == "/redoc":
                self.assertRegex(csp, r"style-src 'self' 'nonce-[A-Za-z0-9_-]+'")
                self.assertIn(
                    "'sha256-QMIg+bpjm3JdElJ388KYke01izlUW0UoNOeKjpMxdgc='",
                    csp,
                )
                self.assertIn(
                    "'sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU='",
                    csp,
                )
                self.assertIn("https://cdn.redoc.ly", csp)
                self.assertIn("worker-src 'self' blob:", csp)


class TestHttpsRedirectMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_production_http_redirects(self) -> None:
        async def call_next(_request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        middleware = HttpsRedirectMiddleware(AsyncMock())
        with patch("app.core.security.settings") as mock_settings:
            mock_settings.is_production = True
            response = await middleware.dispatch(
                _request(
                    "/health",
                    scheme="http",
                    headers=[(b"x-forwarded-proto", b"http")],
                ),
                call_next,
            )
        self.assertEqual(response.status_code, 308)
        self.assertTrue(str(response.headers["location"]).startswith("https://"))

    async def test_development_allows_http(self) -> None:
        async def call_next(_request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        middleware = HttpsRedirectMiddleware(AsyncMock())
        with patch("app.core.security.settings") as mock_settings:
            mock_settings.is_production = False
            response = await middleware.dispatch(
                _request("/health", scheme="http"),
                call_next,
            )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
