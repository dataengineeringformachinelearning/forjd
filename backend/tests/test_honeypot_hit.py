"""Honeypot hit endpoint hardening — no enumeration via 404."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.api.v1.domain import HoneypotHitRequest, honeypot_hit


class TestHoneypotHit(unittest.IsolatedAsyncioTestCase):
    async def test_missing_honeypot_still_returns_ok(self) -> None:
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db_pool=object())))
        body = HoneypotHitRequest(tenant_id=uuid4(), path="/trap")
        with patch(
            "app.api.v1.domain.honeypot_svc.log_interaction",
            new=AsyncMock(return_value=None),
        ) as log_hit:
            result = await honeypot_hit(request, body)

        self.assertEqual(result, {"ok": True})
        self.assertNotIn("interaction", result)
        log_hit.assert_awaited_once()

    async def test_found_honeypot_does_not_leak_interaction(self) -> None:
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db_pool=object())))
        body = HoneypotHitRequest(tenant_id=uuid4(), path="/trap")
        with patch(
            "app.api.v1.domain.honeypot_svc.log_interaction",
            new=AsyncMock(return_value={"id": "hit-1", "honeypot_id": "hp-1"}),
        ):
            result = await honeypot_hit(request, body)

        self.assertEqual(result, {"ok": True})
        self.assertNotIn("interaction", result)


if __name__ == "__main__":
    unittest.main()
