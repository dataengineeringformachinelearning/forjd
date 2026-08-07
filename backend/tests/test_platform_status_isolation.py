"""Platform status slug is reserved and immutable at the service layer."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.core.auth import AuthUser, PrincipalKind
from app.services import status as status_svc


class PlatformStatusIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_page_rejects_platform_status_slug(self) -> None:
        pool = MagicMock()
        user = AuthUser(
            user_id="svc",
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
        )
        with (
            patch.object(status_svc.tenant_svc, "ensure_secure_schema", new=AsyncMock()),
            patch.object(status_svc.tenant_svc, "require_tenant_access", new=AsyncMock()),
            self.assertRaisesRegex(ValueError, "reserved"),
        ):
            await status_svc.create_page(
                pool,
                user=user,
                tenant_id=uuid4(),
                slug="platform-status",
                title="Nope",
            )

    async def test_delete_page_rejects_platform_status(self) -> None:
        pool = MagicMock()
        user = AuthUser(
            user_id="svc",
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
        )
        page_id = uuid4()
        tenant_id = uuid4()
        with (
            patch.object(status_svc.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(
                status_svc,
                "_require_page",
                new=AsyncMock(return_value={"id": str(page_id), "slug": "platform-status"}),
            ),
            self.assertRaisesRegex(ValueError, "immutable"),
        ):
            await status_svc.delete_page(pool, user=user, tenant_id=tenant_id, page_id=page_id)


if __name__ == "__main__":
    unittest.main()
