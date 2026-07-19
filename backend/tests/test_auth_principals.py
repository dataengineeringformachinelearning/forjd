"""Unit tests for user vs service principal shaping (no live JWKS)."""

from __future__ import annotations

import asyncio
import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from fastapi import HTTPException
from starlette.requests import Request

from app.core.auth import (
    SERVICE_TOKEN_PREFIX,
    AuthUser,
    PrincipalKind,
    _authenticate_opaque_service,
    _forjd_metadata,
    _principal_from_claims,
    hash_service_token,
    looks_like_service_token,
    require_user_principal,
    service_token_prefix,
)
from app.core.config import settings
from app.models.service_account import ServiceAccountCreate
from app.services import service_accounts as service_account_svc
from app.services.service_accounts import ALLOWED_SCOPES, DEFAULT_SCOPES, _normalize_scopes
from app.services.tenants import require_tenant_access


class TestServiceScopes(unittest.TestCase):
    def test_default_scopes_cover_partner_surfaces(self) -> None:
        required = {
            "ingest:write",
            "sessions:write",
            "replay:write",
            "status:write",
            "analytics:read",
            "ml:read",
            "exports:read",
            "vulnerabilities:read",
            "integrations:write",
        }
        self.assertTrue(required.issubset(set(DEFAULT_SCOPES)))
        self.assertIn("analytics:write", ALLOWED_SCOPES)
        self.assertNotIn("analytics:write", DEFAULT_SCOPES)
        # Least privilege: erase is allowlisted but opt-in at mint/remint.
        self.assertNotIn("tenants:erase", DEFAULT_SCOPES)
        self.assertIn("tenants:erase", ALLOWED_SCOPES)

    def test_create_body_uses_canonical_defaults_and_erase_is_opt_in(self) -> None:
        tenant_id = UUID("33333333-3333-3333-3333-333333333333")
        ordinary = ServiceAccountCreate(tenant_id=tenant_id, name="partner")
        self.assertFalse(ordinary.include_tenant_erase)
        self.assertEqual(_normalize_scopes(ordinary.scopes), list(DEFAULT_SCOPES))

        erase = ServiceAccountCreate(
            tenant_id=tenant_id,
            name="partner-delete",
            include_tenant_erase=True,
        )
        resolved = _normalize_scopes(
            erase.scopes,
            include_tenant_erase=erase.include_tenant_erase,
        )
        self.assertEqual(resolved[:-1], list(DEFAULT_SCOPES))
        self.assertEqual(resolved[-1], "tenants:erase")
        self.assertEqual(resolved.count("tenants:erase"), 1)

    def test_erase_flag_extends_an_explicit_scope_list(self) -> None:
        self.assertEqual(
            _normalize_scopes(
                ["ingest:write", "tenants:erase"],
                include_tenant_erase=True,
            ),
            ["ingest:write", "tenants:erase"],
        )


class TestServiceTokenShape(unittest.TestCase):
    def test_looks_like_service_token(self) -> None:
        self.assertTrue(looks_like_service_token(f"{SERVICE_TOKEN_PREFIX}abcd1234_secretvalue"))
        self.assertFalse(looks_like_service_token("not-a-service-token"))
        self.assertFalse(looks_like_service_token(f"{SERVICE_TOKEN_PREFIX}short_x"))
        self.assertEqual(
            service_token_prefix(f"{SERVICE_TOKEN_PREFIX}abcd1234_secret"),
            "abcd1234",
        )

    def test_hash_service_token_sha256(self) -> None:
        token = f"{SERVICE_TOKEN_PREFIX}abcd1234_abc"
        self.assertEqual(
            hash_service_token(token),
            hashlib.sha256(token.encode()).hexdigest(),
        )


def _request_for_route(*, method: str, route_path: str, tenant_id: UUID) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": route_path.replace("{tenant_id}", str(tenant_id)),
        "raw_path": b"",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 443),
        "route": SimpleNamespace(path=route_path),
        "path_params": {"tenant_id": str(tenant_id)},
        "app": MagicMock(),
    }
    return Request(scope)


class TestErasedCredentialAuthentication(unittest.IsolatedAsyncioTestCase):
    async def test_completed_tombstone_authenticates_exact_erase_retry_only(self) -> None:
        tenant_id = UUID("33333333-3333-3333-3333-333333333333")
        token = f"{SERVICE_TOKEN_PREFIX}abcd1234_secret"
        route_path = f"{settings.API_V1_STR}/tenants/{{tenant_id}}/erase"
        request = _request_for_route(
            method="POST",
            route_path=route_path,
            tenant_id=tenant_id,
        )
        tombstone = {
            "tenant_id": str(tenant_id),
            "requested_by": "svc:deleted",
            "erased_credential_prefix": "abcd1234",
            "completed_at": object(),
        }
        active = AsyncMock(return_value=None)
        erased = AsyncMock(return_value=tombstone)
        with (
            patch.object(service_account_svc, "authenticate_opaque", active),
            patch.object(service_account_svc, "authenticate_erased_opaque", erased),
        ):
            principal = await _authenticate_opaque_service(
                MagicMock(),
                token,
                request=request,
            )

        self.assertEqual(principal.kind, PrincipalKind.ERASE_TOMBSTONE)
        self.assertEqual(principal.tenant_id, str(tenant_id))
        self.assertFalse(principal.scopes)
        erased.assert_awaited_once()

    async def test_tombstone_is_not_consulted_for_any_other_route(self) -> None:
        tenant_id = UUID("33333333-3333-3333-3333-333333333333")
        token = f"{SERVICE_TOKEN_PREFIX}abcd1234_secret"
        request = _request_for_route(
            method="POST",
            route_path=f"{settings.API_V1_STR}/ingest",
            tenant_id=tenant_id,
        )
        active = AsyncMock(return_value=None)
        erased = AsyncMock()
        with (
            patch.object(service_account_svc, "authenticate_opaque", active),
            patch.object(service_account_svc, "authenticate_erased_opaque", erased),
            self.assertRaises(HTTPException) as raised,
        ):
            await _authenticate_opaque_service(MagicMock(), token, request=request)

        self.assertEqual(raised.exception.status_code, 401)
        erased.assert_not_awaited()

    async def test_tombstone_is_not_consulted_for_get_on_erase_route(self) -> None:
        tenant_id = UUID("33333333-3333-3333-3333-333333333333")
        token = f"{SERVICE_TOKEN_PREFIX}abcd1234_secret"
        request = _request_for_route(
            method="GET",
            route_path=f"{settings.API_V1_STR}/tenants/{{tenant_id}}/erase",
            tenant_id=tenant_id,
        )
        erased = AsyncMock()
        with (
            patch.object(service_account_svc, "authenticate_opaque", AsyncMock(return_value=None)),
            patch.object(service_account_svc, "authenticate_erased_opaque", erased),
            self.assertRaises(HTTPException) as raised,
        ):
            await _authenticate_opaque_service(MagicMock(), token, request=request)

        self.assertEqual(raised.exception.status_code, 401)
        erased.assert_not_awaited()

    async def test_live_opaque_principal_carries_hash_not_raw_token(self) -> None:
        tenant_id = UUID("33333333-3333-3333-3333-333333333333")
        token = f"{SERVICE_TOKEN_PREFIX}abcd1234_secret"
        request = _request_for_route(
            method="POST",
            route_path=f"{settings.API_V1_STR}/tenants/{{tenant_id}}/erase",
            tenant_id=tenant_id,
        )
        active = AsyncMock(
            return_value={
                "id": UUID("55555555-5555-5555-5555-555555555555"),
                "tenant_id": tenant_id,
                "subprocessor": "partner",
                "scopes": ["tenants:erase"],
            }
        )
        with patch.object(service_account_svc, "authenticate_opaque", active):
            principal = await _authenticate_opaque_service(
                MagicMock(),
                token,
                request=request,
            )

        self.assertEqual(principal.opaque_token_prefix, "abcd1234")
        self.assertEqual(principal.opaque_token_hash, hash_service_token(token))
        self.assertNotIn(token, repr(principal.raw_claims))

        with patch.object(service_account_svc, "authenticate_opaque", active):
            ordinary = await _authenticate_opaque_service(MagicMock(), token)
        self.assertIsNone(ordinary.opaque_token_prefix)
        self.assertIsNone(ordinary.opaque_token_hash)


class TestJwtClaimShaping(unittest.TestCase):
    def test_user_claims_become_user_principal(self) -> None:
        user = _principal_from_claims(
            {
                "sub": "11111111-1111-1111-1111-111111111111",
                "role": "authenticated",
                "email": "a@b.c",
            }
        )
        self.assertEqual(user.kind, PrincipalKind.USER)
        self.assertTrue(user.is_user)
        self.assertEqual(user.actor_id, user.user_id)
        self.assertIsNone(user.tenant_id)

    def test_service_claims_from_app_metadata(self) -> None:
        claims = {
            "sub": "22222222-2222-2222-2222-222222222222",
            "role": "authenticated",
            "app_metadata": {
                "forjd": {
                    "principal_type": "service",
                    "tenant_id": "33333333-3333-3333-3333-333333333333",
                    "subprocessor": "partner-app",
                    "scopes": ["ingest:write", "projections:run"],
                }
            },
        }
        self.assertIsNotNone(_forjd_metadata(claims))
        principal = _principal_from_claims(claims)
        self.assertEqual(principal.kind, PrincipalKind.SERVICE)
        self.assertEqual(principal.tenant_id, "33333333-3333-3333-3333-333333333333")
        self.assertEqual(principal.subprocessor, "partner-app")
        self.assertIn("ingest:write", principal.scopes)
        self.assertTrue(principal.actor_id.startswith("svc:"))

    def test_user_metadata_service_shape_ignored(self) -> None:
        """user_metadata is user-writable — must never grant service principal."""
        claims = {
            "sub": "22222222-2222-2222-2222-222222222222",
            "role": "authenticated",
            "user_metadata": {
                "forjd": {
                    "principal_type": "service",
                    "tenant_id": "33333333-3333-3333-3333-333333333333",
                    "scopes": ["*"],
                }
            },
        }
        self.assertIsNone(_forjd_metadata(claims))
        principal = _principal_from_claims(claims)
        self.assertEqual(principal.kind, PrincipalKind.USER)

    def test_service_role_jwt_rejected(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            _principal_from_claims(
                {"sub": "44444444-4444-4444-4444-444444444444", "role": "service_role"}
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_service_role_rejected_even_with_forjd_claim(self) -> None:
        """service_role must not be salvaged by app_metadata.forjd shaping."""
        with self.assertRaises(HTTPException) as ctx:
            _principal_from_claims(
                {
                    "sub": "44444444-4444-4444-4444-444444444444",
                    "role": "service_role",
                    "app_metadata": {
                        "forjd": {
                            "principal_type": "service",
                            "tenant_id": "33333333-3333-3333-3333-333333333333",
                            "scopes": ["*"],
                        }
                    },
                }
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_require_user_principal_blocks_service(self) -> None:
        svc = AuthUser(
            user_id="55555555-5555-5555-5555-555555555555",
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id="33333333-3333-3333-3333-333333333333",
            scopes=frozenset({"ingest:write"}),
        )
        with self.assertRaises(HTTPException) as ctx:
            require_user_principal(svc)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_require_user_principal_allows_user(self) -> None:
        user = AuthUser(
            user_id="11111111-1111-1111-1111-111111111111",
            email=None,
            role="authenticated",
            raw_claims={},
        )
        self.assertIs(require_user_principal(user), user)


class TestTenantAccess(unittest.TestCase):
    def test_service_isolation_and_scopes(self) -> None:
        bound = "33333333-3333-3333-3333-333333333333"
        other = UUID("66666666-6666-6666-6666-666666666666")
        svc = AuthUser(
            user_id="55555555-5555-5555-5555-555555555555",
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=bound,
            scopes=frozenset({"ingest:write"}),
        )

        async def _run() -> None:
            with self.assertRaises(HTTPException) as mismatch:
                await require_tenant_access(
                    None,  # type: ignore[arg-type]
                    principal=svc,
                    tenant_id=other,
                    required_scopes=frozenset({"ingest:write"}),
                )
            self.assertEqual(mismatch.exception.status_code, 403)

            with self.assertRaises(HTTPException) as scope:
                await require_tenant_access(
                    None,  # type: ignore[arg-type]
                    principal=svc,
                    tenant_id=UUID(bound),
                    required_scopes=frozenset({"projections:run"}),
                )
            self.assertEqual(scope.exception.status_code, 403)

            role = await require_tenant_access(
                None,  # type: ignore[arg-type]
                principal=svc,
                tenant_id=UUID(bound),
                required_scopes=frozenset({"ingest:write"}),
            )
            self.assertEqual(role, "service")

        asyncio.run(_run())

    def test_service_sessions_and_analytics_scopes(self) -> None:
        bound = "33333333-3333-3333-3333-333333333333"
        svc = AuthUser(
            user_id="55555555-5555-5555-5555-555555555555",
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=bound,
            scopes=frozenset(
                {
                    "sessions:write",
                    "sessions:read",
                    "replay:read",
                    "status:write",
                    "analytics:read",
                }
            ),
        )

        async def _run() -> None:
            for scope in (
                "sessions:write",
                "replay:read",
                "status:write",
                "analytics:read",
            ):
                role = await require_tenant_access(
                    None,  # type: ignore[arg-type]
                    principal=svc,
                    tenant_id=UUID(bound),
                    required_scopes=frozenset({scope}),
                )
                self.assertEqual(role, "service")

            with self.assertRaises(HTTPException) as missing:
                await require_tenant_access(
                    None,  # type: ignore[arg-type]
                    principal=svc,
                    tenant_id=UUID(bound),
                    required_scopes=frozenset({"analytics:write"}),
                )
            self.assertEqual(missing.exception.status_code, 403)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
