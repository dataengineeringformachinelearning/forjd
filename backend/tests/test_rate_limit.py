"""Distributed principal and IP rate-limit tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.core.auth import AuthUser, PrincipalKind
from app.core.rate_limit import (
    _client_ip,
    _matches_public_rate_limit,
    enforce_ip_rate_limit,
    enforce_principal_rate_limit,
)


def _request(
    *,
    result: list[int],
    method: str = "POST",
    path: str = "/api/v1/ingest",
    headers: dict[str, str] | None = None,
    client_host: str = "203.0.113.10",
):
    redis = SimpleNamespace(eval=AsyncMock(return_value=result))
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=redis)),
        method=method,
        url=SimpleNamespace(path=path),
        state=SimpleNamespace(),
        headers=headers or {},
        client=SimpleNamespace(host=client_host),
    )


class TestPrincipalRateLimit(unittest.IsolatedAsyncioTestCase):
    async def test_sets_remaining_quota_after_allow(self) -> None:
        request = _request(result=[1, 2, 0])
        principal = AuthUser(
            user_id="service-1",
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
        )
        with patch.object(
            __import__("app.core.rate_limit", fromlist=["settings"]).settings,
            "INGEST_RATE_LIMIT_RPM",
            10,
            create=True,
        ):
            await enforce_principal_rate_limit(request, principal)

        self.assertEqual(request.state.rate_limit["remaining"], 8)

    async def test_rejection_has_retry_after(self) -> None:
        request = _request(result=[0, 10, 2_500])
        principal = AuthUser(
            user_id="service-1",
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
        )
        with (
            patch.object(
                __import__("app.core.rate_limit", fromlist=["settings"]).settings,
                "INGEST_RATE_LIMIT_RPM",
                10,
                create=True,
            ),
            self.assertRaises(HTTPException) as raised,
        ):
            await enforce_principal_rate_limit(request, principal)

        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.headers["Retry-After"], "3")


class TestIpRateLimit(unittest.IsolatedAsyncioTestCase):
    async def test_ip_limiter_sets_remaining(self) -> None:
        request = _request(
            result=[1, 3, 0],
            method="GET",
            path="/api/v1/capabilities",
            headers={"x-forwarded-for": "198.51.100.20, 10.0.0.1"},
        )
        await enforce_ip_rate_limit(request, bucket="public", limit=10)
        self.assertEqual(request.state.rate_limit["remaining"], 7)
        key = request.app.state.redis.eval.await_args.args[2]
        self.assertTrue(key.startswith("forjd:rate-limit:ip:"))
        self.assertTrue(key.endswith(":public"))

    async def test_client_ip_prefers_forwarded_first_hop(self) -> None:
        request = _request(
            result=[1, 1, 0],
            headers={"x-forwarded-for": "198.51.100.20, 10.0.0.1"},
            client_host="127.0.0.1",
        )
        self.assertEqual(_client_ip(request), "198.51.100.20")

    def test_public_route_matcher(self) -> None:
        self.assertTrue(
            _matches_public_rate_limit(
                SimpleNamespace(method="GET", url=SimpleNamespace(path="/api/v1/capabilities"))
            )
        )
        self.assertTrue(
            _matches_public_rate_limit(
                SimpleNamespace(
                    method="GET",
                    url=SimpleNamespace(path="/api/v1/status/pages/slug/acme"),
                )
            )
        )
        self.assertTrue(
            _matches_public_rate_limit(
                SimpleNamespace(method="POST", url=SimpleNamespace(path="/api/v1/honeypots/hit"))
            )
        )
        self.assertFalse(
            _matches_public_rate_limit(
                SimpleNamespace(method="GET", url=SimpleNamespace(path="/api/v1/ingest"))
            )
        )


if __name__ == "__main__":
    unittest.main()
