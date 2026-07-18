"""Unit tests for tenant erase authorization helpers."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.core.auth import AuthUser, PrincipalKind
from app.services import tenant_erase as erase_svc


class TenantEraseTests(unittest.IsolatedAsyncioTestCase):
    async def test_erase_requires_tenant_access(self) -> None:
        pool = MagicMock()
        principal = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(uuid4()),
            scopes=frozenset({"ingest:write"}),
        )
        with patch.object(
            erase_svc.tenant_svc,
            "require_tenant_access",
            new=AsyncMock(side_effect=HTTPException(status_code=403, detail="insufficient")),
        ):
            with self.assertRaises(HTTPException):
                await erase_svc.erase_tenant(pool, principal=principal, tenant_id=uuid4())

    async def test_erase_deletes_in_transaction(self) -> None:
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

        conn = MagicMock()
        conn.execute = AsyncMock(return_value="DELETE 1")
        tx = MagicMock()
        tx.__aenter__ = AsyncMock(return_value=None)
        tx.__aexit__ = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=tx)

        acquire = MagicMock()
        acquire.__aenter__ = AsyncMock(return_value=conn)
        acquire.__aexit__ = AsyncMock(return_value=None)
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=acquire)

        with patch.object(
            erase_svc.tenant_svc,
            "require_tenant_access",
            new=AsyncMock(return_value="service"),
        ):
            result = await erase_svc.erase_tenant(pool, principal=principal, tenant_id=tenant_id)

        self.assertTrue(result["ok"])
        self.assertEqual(result["tenant_id"], str(tenant_id))
        self.assertGreaterEqual(conn.execute.await_count, 3)


if __name__ == "__main__":
    unittest.main()
