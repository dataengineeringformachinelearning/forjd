"""API key middleware must not skip on forged Bearer JWT/fjsvc shapes."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

from app.core.security import ApiKeyMiddleware


def _request(*, method: str = "POST", path: str = "/api/v1/honeypots/hit", headers: dict[str, str]):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("203.0.113.10", 12345),
        "server": ("test", 443),
    }
    return Request(scope)


class TestApiKeyMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_forged_bearer_jwt_shape_does_not_bypass_api_key(self) -> None:
        middleware = ApiKeyMiddleware(app=AsyncMock())
        call_next = AsyncMock(return_value=SimpleNamespace(status_code=200))
        request = _request(headers={"authorization": "Bearer a.b.c"})
        with patch("app.core.security.settings") as settings:
            settings.API_KEY = "platform-secret"
            settings.API_V1_STR = "/api/v1"
            settings.FORJD_PROVISION_TOKEN = ""
            response = await middleware.dispatch(request, call_next)
        self.assertEqual(response.status_code, 401)
        call_next.assert_not_awaited()

    async def test_x_api_key_allows_mutating_route(self) -> None:
        middleware = ApiKeyMiddleware(app=AsyncMock())
        call_next = AsyncMock(return_value=SimpleNamespace(status_code=200))
        request = _request(headers={"x-api-key": "platform-secret"})
        with patch("app.core.security.settings") as settings:
            settings.API_KEY = "platform-secret"
            settings.API_V1_STR = "/api/v1"
            settings.FORJD_PROVISION_TOKEN = ""
            response = await middleware.dispatch(request, call_next)
        self.assertEqual(response.status_code, 200)
        call_next.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
