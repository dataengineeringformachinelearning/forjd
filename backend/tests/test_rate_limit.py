"""Distributed principal rate-limit tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.core.auth import AuthUser, PrincipalKind
from app.core.rate_limit import enforce_principal_rate_limit


def _request(*, result: list[int], method: str = "POST", path: str = "/api/v1/ingest"):
    redis = SimpleNamespace(eval=AsyncMock(return_value=result))
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=redis)),
        method=method,
        url=SimpleNamespace(path=path),
        state=SimpleNamespace(),
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


if __name__ == "__main__":
    unittest.main()
