"""Unit tests for user vs service principal shaping (no live JWKS)."""

from __future__ import annotations

import asyncio
import hashlib
import unittest
from uuid import UUID

from fastapi import HTTPException

from app.core.auth import (
    SERVICE_TOKEN_PREFIX,
    AuthUser,
    PrincipalKind,
    _forjd_metadata,
    _principal_from_claims,
    hash_service_token,
    looks_like_service_token,
    require_user_principal,
    service_token_prefix,
)
from app.services.service_accounts import ALLOWED_SCOPES, DEFAULT_SCOPES
from app.services.tenants import require_tenant_access


class TestServiceScopes(unittest.TestCase):
    def test_default_scopes_cover_cutover_surfaces(self) -> None:
        required = {
            "ingest:write",
            "sessions:write",
            "replay:write",
            "status:write",
            "analytics:read",
        }
        self.assertTrue(required.issubset(set(DEFAULT_SCOPES)))
        self.assertIn("analytics:write", ALLOWED_SCOPES)
        self.assertNotIn("analytics:write", DEFAULT_SCOPES)


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

    def test_service_role_jwt_rejected(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            _principal_from_claims(
                {"sub": "44444444-4444-4444-4444-444444444444", "role": "service_role"}
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
