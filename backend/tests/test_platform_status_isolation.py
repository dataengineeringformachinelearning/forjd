"""Platform status slug is reserved and immutable at the service layer."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import Request

from app.api.v1 import status as status_api
from app.core.auth import AuthUser, PrincipalKind
from app.services import status as status_svc


class PlatformStatusIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_page_strips_tenant_for_foreign_service(self) -> None:
        page_tenant = str(uuid4())
        foreign = AuthUser(
            user_id="svc-foreign",
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(uuid4()),
            scopes=frozenset({"status:read"}),
        )
        page = {
            "id": str(uuid4()),
            "tenant_id": page_tenant,
            "slug": "customer-site",
            "title": "Customer",
            "is_published": True,
        }
        request = MagicMock(spec=Request)
        request.app = MagicMock()
        with (
            patch.object(
                status_api.status_svc,
                "get_published_page",
                new=AsyncMock(return_value=dict(page)),
            ),
            patch.object(status_api, "_pool", return_value=MagicMock()),
        ):
            body = await status_api.public_page(request, slug="customer-site", user=foreign)
        self.assertNotIn("tenant_id", body["page"])

    async def test_public_page_keeps_tenant_for_bound_service(self) -> None:
        page_tenant = str(uuid4())
        owner = AuthUser(
            user_id="svc-owner",
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=page_tenant,
            scopes=frozenset({"status:read"}),
        )
        page = {
            "id": str(uuid4()),
            "tenant_id": page_tenant,
            "slug": "customer-site",
            "title": "Customer",
            "is_published": True,
        }
        request = MagicMock(spec=Request)
        with (
            patch.object(
                status_api.status_svc,
                "get_published_page",
                new=AsyncMock(return_value=dict(page)),
            ),
            patch.object(status_api, "_pool", return_value=MagicMock()),
        ):
            body = await status_api.public_page(request, slug="customer-site", user=owner)
        self.assertEqual(body["page"]["tenant_id"], page_tenant)

    async def test_public_page_keeps_tenant_for_resolve_scope(self) -> None:
        page_tenant = str(uuid4())
        platform = AuthUser(
            user_id="svc-platform",
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(uuid4()),
            scopes=frozenset({"status:tenant-resolve"}),
        )
        page = {
            "id": str(uuid4()),
            "tenant_id": page_tenant,
            "slug": "customer-site",
            "title": "Customer",
            "is_published": True,
        }
        request = MagicMock(spec=Request)
        with (
            patch.object(
                status_api.status_svc,
                "get_published_page",
                new=AsyncMock(return_value=dict(page)),
            ),
            patch.object(status_api, "_pool", return_value=MagicMock()),
        ):
            body = await status_api.public_page(request, slug="customer-site", user=platform)
        self.assertEqual(body["page"]["tenant_id"], page_tenant)

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
