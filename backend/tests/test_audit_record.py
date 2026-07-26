"""Integration-style tests for audit.record — sanitize before insert."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services import audit


class TestAuditRecord(unittest.IsolatedAsyncioTestCase):
    async def test_record_inserts_sanitized_details_only(self) -> None:
        pool = MagicMock()
        pool.execute = AsyncMock(return_value="INSERT 0 1")

        tenant = uuid4()
        await audit.record(
            pool,
            action=audit.ACTION_INGEST_BATCH,
            actor_user_id="svc:test",
            tenant_id=tenant,
            resource_type="batch",
            resource_id="batch-1",
            details={
                "accepted": 2,
                "ciphertext": "should-not-persist",
                "token": "fjsvc_leak",
                "has_opaque": True,
            },
        )

        pool.execute.assert_awaited()
        args = pool.execute.await_args
        sql = args.args[0]
        self.assertIn("INSERT INTO audit_events", sql)
        # positional: actor, tenant, action, resource_type, resource_id, details_json
        details_json = args.args[6]
        self.assertIn("accepted", details_json)
        self.assertIn("has_opaque", details_json)
        self.assertNotIn("ciphertext", details_json)
        self.assertNotIn("fjsvc_leak", details_json)
        self.assertNotIn('"token"', details_json)

    async def test_record_required_propagates_db_errors(self) -> None:
        pool = MagicMock()
        pool.execute = AsyncMock(side_effect=RuntimeError("db down"))

        with self.assertRaises(RuntimeError):
            await audit.record_required(
                pool,
                action="service_account.create",
                actor_user_id="user:1",
                tenant_id=uuid4(),
                details={"ok": True},
            )


if __name__ == "__main__":
    unittest.main()
