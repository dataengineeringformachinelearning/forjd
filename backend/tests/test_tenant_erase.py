"""Unit tests for tenant erase authorization helpers."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.core.auth import AuthUser, PrincipalKind, hash_service_token
from app.services import tenant_erase as erase_svc


class TenantEraseTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_receipt_makes_retry_idempotent(self) -> None:
        tenant_id = uuid4()
        principal = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(tenant_id),
            scopes=frozenset({"tenants:erase"}),
        )
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            return_value={
                "tenant_id": str(tenant_id),
                "requested_by": principal.actor_id,
                "status": "completed",
                "deleted_counts": {"tenants": 1},
                "completed_at": datetime.now(UTC),
            }
        )
        authorize = AsyncMock()
        with patch.object(erase_svc.tenant_svc, "require_tenant_access", authorize):
            result = await erase_svc.erase_tenant(
                pool,
                principal=principal,
                tenant_id=tenant_id,
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["idempotent_replay"])
        authorize.assert_not_awaited()

    async def test_erased_credential_can_only_read_its_completed_receipt(self) -> None:
        tenant_id = uuid4()
        principal = AuthUser(
            user_id="erased:abcd1234",
            email=None,
            role="erase_tombstone",
            raw_claims={"auth": "erased_opaque_tombstone"},
            kind=PrincipalKind.ERASE_TOMBSTONE,
            tenant_id=str(tenant_id),
        )
        completed = {
            "tenant_id": str(tenant_id),
            "requested_by": "svc:deleted",
            "status": "completed",
            "deleted_counts": {"tenants": 1},
            "completed_at": datetime.now(UTC),
        }
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=completed)
        authorize = AsyncMock()
        with patch.object(erase_svc.tenant_svc, "require_tenant_access", authorize):
            result = await erase_svc.erase_tenant(
                pool,
                principal=principal,
                tenant_id=tenant_id,
            )
        self.assertTrue(result["idempotent_replay"])
        authorize.assert_not_awaited()

        pool.fetchrow = AsyncMock(return_value=None)
        with self.assertRaises(HTTPException) as raised:
            await erase_svc.erase_tenant(
                pool,
                principal=principal,
                tenant_id=tenant_id,
            )
        self.assertEqual(raised.exception.status_code, 403)

    async def test_erase_requires_tenant_access(self) -> None:
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        principal = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(uuid4()),
            scopes=frozenset({"ingest:write"}),
        )
        with (
            patch.object(
                erase_svc.tenant_svc,
                "require_tenant_access",
                new=AsyncMock(side_effect=HTTPException(status_code=403, detail="insufficient")),
            ),
            self.assertRaises(HTTPException),
        ):
            await erase_svc.erase_tenant(pool, principal=principal, tenant_id=uuid4())

    async def test_other_service_without_erase_scope_cannot_read_receipt(self) -> None:
        tenant_id = uuid4()
        principal = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(tenant_id),
            scopes=frozenset({"ingest:write"}),
        )
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            return_value={
                "tenant_id": str(tenant_id),
                "requested_by": "svc:another-account",
                "status": "completed",
                "deleted_counts": {"tenants": 1},
                "completed_at": datetime.now(UTC),
            }
        )
        authorize = AsyncMock(side_effect=HTTPException(status_code=403, detail="insufficient"))
        with (
            patch.object(erase_svc.tenant_svc, "require_tenant_access", authorize),
            self.assertRaises(HTTPException) as raised,
        ):
            await erase_svc.erase_tenant(
                pool,
                principal=principal,
                tenant_id=tenant_id,
            )
        self.assertEqual(raised.exception.status_code, 403)
        authorize.assert_awaited_once()

    async def test_erase_deletes_in_transaction(self) -> None:
        tenant_id = uuid4()
        token = "fjsvc_abcd1234_secret"
        principal = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(tenant_id),
            scopes=frozenset({"tenants:erase"}),
            opaque_token_prefix="abcd1234",
            opaque_token_hash=hash_service_token(token),
        )

        conn = MagicMock()
        conn.execute = AsyncMock(return_value="DELETE 1")
        conn.fetchval = AsyncMock(side_effect=[True, True, False])
        conn.fetch = AsyncMock(return_value=[{"table_name": "service_accounts"}])
        conn.fetchrow = AsyncMock(
            side_effect=[
                None,
                {
                    "tenant_id": str(tenant_id),
                    "requested_by": principal.actor_id,
                    "status": "completed",
                    "deleted_counts": {"ingest_processing_batches": 1, "tenants": 1},
                    "completed_at": datetime.now(UTC),
                },
            ]
        )
        tx = MagicMock()
        tx.__aenter__ = AsyncMock(return_value=None)
        tx.__aexit__ = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=tx)

        acquire = MagicMock()
        acquire.__aenter__ = AsyncMock(return_value=conn)
        acquire.__aexit__ = AsyncMock(return_value=None)
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=acquire)
        pool.fetchrow = AsyncMock(return_value=None)

        with patch.object(
            erase_svc.tenant_svc,
            "require_tenant_access",
            new=AsyncMock(return_value="service"),
        ):
            result = await erase_svc.erase_tenant(pool, principal=principal, tenant_id=tenant_id)

        self.assertTrue(result["ok"])
        self.assertEqual(result["tenant_id"], str(tenant_id))
        self.assertGreaterEqual(conn.execute.await_count, 3)
        receipt_insert = next(
            call
            for call in conn.execute.await_args_list
            if "INSERT INTO tenant_erase_receipts" in call.args[0]
        )
        self.assertEqual(receipt_insert.args[3], "abcd1234")
        self.assertEqual(receipt_insert.args[4], hash_service_token(token))
        self.assertNotIn(token, receipt_insert.args)
        processing_delete = next(
            call
            for call in conn.execute.await_args_list
            if "DELETE FROM public.ingest_processing_batches" in call.args[0]
        )
        self.assertEqual(processing_delete.args[1], str(tenant_id))
        self.assertEqual(result["deleted"]["ingest_processing_batches"], 1)
        receipt_update = next(
            call
            for call in conn.fetchrow.await_args_list
            if "UPDATE tenant_erase_receipts" in call.args[0]
        )
        self.assertEqual(
            json.loads(receipt_update.args[2])["ingest_processing_batches"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
