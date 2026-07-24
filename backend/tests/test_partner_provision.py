"""Focused tests for isolated, idempotent partner provisioning."""

from __future__ import annotations

import asyncio
import copy
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID

from app.services import partner_provision as provision_svc
from app.services import service_accounts as sa_svc

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_REF = "account:efeff1e1-14c6-4d13-b3fa-be4316c3f783"


class _ProvisionStore:
    def __init__(self) -> None:
        self.provisions: dict[tuple[str, str], dict[str, str]] = {}
        self.tenants: dict[str, dict[str, object]] = {}
        self.service_accounts: dict[str, dict[str, object]] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.lock_keys: list[str] = []
        self.tenant_sequence = 0
        self.service_account_sequence = 0

    def new_tenant(self, slug: str, name: str) -> dict[str, object]:
        self.tenant_sequence += 1
        tenant_id = str(UUID(int=self.tenant_sequence))
        row: dict[str, object] = {
            "id": tenant_id,
            "slug": slug,
            "name": name,
            "key_directory_id": None,
            "created_at": datetime.now(UTC),
        }
        self.tenants[tenant_id] = row
        return row

    def new_service_account(
        self,
        tenant_id: str,
        name: str,
        partner: str,
        prefix: str,
        scopes: list[str],
    ) -> dict[str, object]:
        self.service_account_sequence += 1
        account_id = str(UUID(int=10_000 + self.service_account_sequence))
        now = datetime.now(UTC)
        row: dict[str, object] = {
            "id": account_id,
            "tenant_id": tenant_id,
            "name": name,
            "subprocessor": partner,
            "prefix": prefix,
            "auth_user_id": None,
            "scopes": scopes,
            "is_active": True,
            "revoked_at": None,
            "created_by": None,
            "created_at": now,
            "updated_at": now,
            "last_used_at": None,
        }
        self.service_accounts[account_id] = row
        return row


class _Transaction:
    def __init__(self, conn: _Connection) -> None:
        self.conn = conn
        self.snapshot: (
            tuple[
                dict[tuple[str, str], dict[str, str]],
                dict[str, dict[str, object]],
                dict[str, dict[str, object]],
                int,
                int,
            ]
            | None
        ) = None

    async def __aenter__(self) -> None:
        store = self.conn.store
        self.snapshot = (
            copy.deepcopy(store.provisions),
            copy.deepcopy(store.tenants),
            copy.deepcopy(store.service_accounts),
            store.tenant_sequence,
            store.service_account_sequence,
        )
        self.conn.in_transaction = True
        return None

    async def __aexit__(self, exc_type: object, *_args: object) -> None:
        if exc_type is not None and self.snapshot is not None:
            store = self.conn.store
            (
                store.provisions,
                store.tenants,
                store.service_accounts,
                store.tenant_sequence,
                store.service_account_sequence,
            ) = self.snapshot
        self.conn.in_transaction = False
        if self.conn.held_lock is not None:
            self.conn.held_lock.release()
            self.conn.held_lock = None


class _Connection:
    def __init__(self, store: _ProvisionStore) -> None:
        self.store = store
        self.held_lock: asyncio.Lock | None = None
        self.in_transaction = False

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    async def fetchval(self, query: str, lock_key: str) -> None:
        if "pg_advisory_xact_lock" not in query:
            raise AssertionError(query)
        lock = self.store.locks.setdefault(lock_key, asyncio.Lock())
        self.store.lock_keys.append(lock_key)
        await lock.acquire()
        self.held_lock = lock
        await asyncio.sleep(0)

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM partner_provisions" in query:
            partner, external_ref = (str(arg) for arg in args)
            return self.store.provisions.get((partner, external_ref))
        if "INSERT INTO tenants" in query:
            return self.store.new_tenant(str(args[0]), str(args[1]))
        if "INSERT INTO service_accounts" in query:
            return self.store.new_service_account(
                str(args[0]),
                str(args[1]),
                str(args[2]),
                str(args[3]),
                list(args[5]),  # type: ignore[arg-type]
            )
        if "FROM tenants WHERE" in query:
            return self.store.tenants[str(args[0])]
        if "FROM service_accounts" in query:
            account = self.store.service_accounts[str(args[0])]
            if len(args) > 1 and account["tenant_id"] != str(args[1]):
                return None
            return account
        raise AssertionError(query)

    async def execute(self, query: str, *args: object) -> str:
        if "INSERT INTO partner_provisions" in query:
            external_ref, partner, tenant_id, service_account_id = (str(arg) for arg in args)
            self.store.provisions[(partner, external_ref)] = {
                "id": str(UUID(int=20_000 + len(self.store.provisions))),
                "tenant_id": tenant_id,
                "service_account_id": service_account_id,
            }
            return "INSERT 0 1"
        if "UPDATE service_accounts" in query:
            account = self.store.service_accounts[str(args[0])]
            if account["tenant_id"] != str(args[1]):
                return "UPDATE 0"
            account["is_active"] = False
            account["revoked_at"] = datetime.now(UTC)
            return "UPDATE 1"
        if "UPDATE partner_provisions" in query:
            partner, external_ref, service_account_id = (str(arg) for arg in args)
            self.store.provisions[(partner, external_ref)]["service_account_id"] = (
                service_account_id
            )
            return "UPDATE 1"
        raise AssertionError(query)


class _Acquire:
    def __init__(self, store: _ProvisionStore) -> None:
        self.store = store

    async def __aenter__(self) -> _Connection:
        return _Connection(self.store)

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Pool:
    def __init__(self) -> None:
        self.store = _ProvisionStore()

    def acquire(self) -> _Acquire:
        return _Acquire(self.store)


class TestPartnerProvisionHelpers(unittest.TestCase):
    def test_slug_namespace_is_stable_and_partner_bound(self) -> None:
        deml_a = provision_svc._slug_for_external_ref(
            EXTERNAL_REF,
            partner="deml",
            explicit=None,
        )
        deml_b = provision_svc._slug_for_external_ref(
            EXTERNAL_REF,
            partner="deml",
            explicit=None,
        )
        other = provision_svc._slug_for_external_ref(
            EXTERNAL_REF,
            partner="other",
            explicit=None,
        )
        self.assertEqual(deml_a, deml_b)
        self.assertNotEqual(deml_a, other)
        self.assertTrue(deml_a.startswith("deml-"))
        self.assertLessEqual(len(deml_a), 63)

    def test_explicit_slug(self) -> None:
        self.assertEqual(
            provision_svc._slug_for_external_ref(
                EXTERNAL_REF,
                explicit="Acme-Tenant",
            ),
            "acme-tenant",
        )

    def test_deml_scope_profile_is_explicit_and_ml_write_capable(self) -> None:
        scopes = provision_svc._scopes_for_partner(
            "deml",
            include_tenant_erase=False,
        )
        self.assertEqual(scopes, list(provision_svc.DEML_PROVISION_SCOPES))
        self.assertIn("ml:write", scopes)
        self.assertNotIn("*", scopes)
        self.assertNotIn("tenants:erase", scopes)
        self.assertNotIn("ml:write", sa_svc.DEFAULT_SCOPES)
        self.assertTrue(set(scopes).issubset(sa_svc.ALLOWED_SCOPES))

    def test_non_deml_partner_keeps_generic_defaults(self) -> None:
        scopes = provision_svc._scopes_for_partner(
            "other",
            include_tenant_erase=False,
        )
        self.assertEqual(scopes, list(sa_svc.DEFAULT_SCOPES))
        self.assertNotIn("ml:write", scopes)

    def test_blank_or_invalid_partner_is_not_coerced_to_deml(self) -> None:
        for partner in ("", "   ", "../deml", "deml:other"):
            with self.subTest(partner=partner), self.assertRaises(ValueError):
                provision_svc._normalize_partner(partner)

    def test_migration_replaces_global_external_ref_uniqueness(self) -> None:
        sql = (ROOT / "sql/027_partner_provision_isolation.sql").read_text()
        self.assertIn("(partner, external_ref)", sql)
        self.assertIn("DROP CONSTRAINT IF EXISTS partner_provisions_external_ref_key", sql)
        self.assertIn("partner_provisions_partner_format", sql)

    def test_migration_upgrades_only_active_deml_credentials(self) -> None:
        sql = (ROOT / "sql/027_partner_provision_isolation.sql").read_text()
        for contract in (
            "array_append(sa.scopes, 'ml:write')",
            "LOWER(BTRIM(COALESCE(sa.subprocessor, ''))) = 'deml'",
            "OR EXISTS",
            "pp.service_account_id = sa.id",
            "LOWER(BTRIM(pp.partner)) = 'deml'",
            "sa.is_active",
            "sa.revoked_at IS NULL",
            "NOT ('ml:write' = ANY(sa.scopes))",
        ):
            self.assertIn(contract, sql)

    def test_migration_enforces_credential_tenant_integrity(self) -> None:
        sql = (ROOT / "sql/027_partner_provision_isolation.sql").read_text()
        for contract in (
            "partner_provisions_tenant_uidx",
            "partner_provisions_service_account_uidx",
            "duplicate tenant mappings",
            "duplicate service-account mappings",
            "service_accounts_id_tenant_uidx",
            "service_account_id/tenant_id mismatch",
            "FOREIGN KEY (service_account_id, tenant_id)",
            "REFERENCES public.service_accounts (id, tenant_id)",
            "VALIDATE CONSTRAINT partner_provisions_service_account_tenant_fkey",
            "DROP CONSTRAINT IF EXISTS partner_provisions_service_account_id_fkey",
            "service_accounts_auth_or_opaque",
            "NOT is_active",
            "revoked_at IS NULL",
            "pg_get_indexdef",
            "unexpected definition",
        ):
            self.assertIn(contract, sql)
        self.assertLess(
            sql.index("VALIDATE CONSTRAINT partner_provisions_service_account_tenant_fkey"),
            sql.index("DROP CONSTRAINT IF EXISTS partner_provisions_service_account_id_fkey"),
        )

    def test_post_migration_verifier_requires_partner_contracts(self) -> None:
        verifier = (ROOT / "scripts/verify_supabase_post_migration.py").read_text()
        for contract in (
            "partner_provisions_partner_external_ref_uidx",
            "partner_provisions_tenant_uidx",
            "partner_provisions_service_account_uidx",
            "service_accounts_id_tenant_uidx",
            "partner_provisions_partner_format",
            "partner_provisions_service_account_tenant_fkey",
            "contract_partner_provision_duplicates",
            "contract_partner_provision_tenant_mismatch",
            "contract_partner_provision_tenant_aliases",
            "contract_partner_provision_credential_aliases",
            "contract_active_deml_ml_write",
            "pg_get_indexdef",
        ):
            self.assertIn(contract, verifier)
        self.assertIn('"constraint_",', verifier)
        self.assertIn('"contract_",', verifier)


class TestPartnerProvisionSemantics(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.ensure_patch = patch.object(
            provision_svc,
            "ensure_partner_provision_schema",
            new=AsyncMock(),
        )
        self.audit_patch = patch.object(
            provision_svc.audit,
            "record_required",
            new=AsyncMock(),
        )
        self.ensure_patch.start()
        self.audit_required = self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)
        self.addCleanup(self.ensure_patch.stop)

    async def _provision(
        self,
        pool: _Pool,
        *,
        partner: str = "deml",
        remint_if_exists: bool = False,
    ) -> dict[str, object]:
        return await provision_svc.provision_partner_tenant(
            pool,  # type: ignore[arg-type]
            external_ref=EXTERNAL_REF,
            partner=partner,
            include_tenant_erase=False,
            remint_if_exists=remint_if_exists,
        )

    async def test_idempotent_retry_returns_same_tenant_without_token(self) -> None:
        pool = _Pool()
        first = await self._provision(pool)
        second = await self._provision(pool)

        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["tenant"], second["tenant"])
        self.assertIsNotNone(first["service_account"]["token"])  # type: ignore[index]
        self.assertIsNone(second["service_account"]["token"])  # type: ignore[index]
        self.assertEqual(pool.store.tenant_sequence, 1)
        self.assertEqual(pool.store.service_account_sequence, 1)

    async def test_same_external_ref_is_isolated_by_partner(self) -> None:
        pool = _Pool()
        deml = await self._provision(pool, partner="deml")
        other = await self._provision(pool, partner="other")

        self.assertNotEqual(deml["tenant"], other["tenant"])
        self.assertEqual(
            set(pool.store.provisions),
            {("deml", EXTERNAL_REF), ("other", EXTERNAL_REF)},
        )

    async def test_concurrent_first_provision_serializes_to_one_mapping(self) -> None:
        pool = _Pool()
        first, second = await asyncio.gather(
            self._provision(pool),
            self._provision(pool),
        )

        self.assertEqual(sorted((bool(first["created"]), bool(second["created"]))), [False, True])
        self.assertEqual(pool.store.tenant_sequence, 1)
        self.assertEqual(pool.store.service_account_sequence, 1)
        self.assertEqual(len(pool.store.provisions), 1)
        self.assertEqual(len(pool.store.lock_keys), 2)
        self.assertEqual(pool.store.lock_keys[0], pool.store.lock_keys[1])

    async def test_remint_rotates_account_and_uses_deml_scope_profile(self) -> None:
        pool = _Pool()
        initial = await self._provision(pool)
        reminted = await self._provision(pool, remint_if_exists=True)

        self.assertFalse(reminted["created"])
        self.assertTrue(reminted["reminted"])
        self.assertEqual(initial["tenant"], reminted["tenant"])
        self.assertEqual(pool.store.service_account_sequence, 2)
        self.assertIn("ml:write", reminted["service_account"]["scopes"])  # type: ignore[index]

    async def test_corrupt_cross_tenant_mapping_fails_read_and_repairs_without_revocation(
        self,
    ) -> None:
        pool = _Pool()
        initial = await self._provision(pool)
        mapping = pool.store.provisions[("deml", EXTERNAL_REF)]
        foreign_tenant = pool.store.new_tenant("foreign", "Foreign")
        foreign_account = pool.store.new_service_account(
            str(foreign_tenant["id"]),
            "foreign-runtime",
            "deml",
            "deadbeef",
            list(provision_svc.DEML_PROVISION_SCOPES),
        )
        mapping["service_account_id"] = str(foreign_account["id"])

        with self.assertRaisesRegex(RuntimeError, "tenant integrity violation"):
            await self._provision(pool)

        reminted = await self._provision(pool, remint_if_exists=True)
        self.assertEqual(reminted["tenant"], initial["tenant"])
        self.assertTrue(pool.store.service_accounts[str(foreign_account["id"])]["is_active"])
        self.assertNotEqual(
            pool.store.provisions[("deml", EXTERNAL_REF)]["service_account_id"],
            foreign_account["id"],
        )

    async def test_required_audit_is_atomic_with_provision(self) -> None:
        pool = _Pool()
        observed_transaction_state: list[bool] = []

        async def fail_audit(conn: _Connection, **_kwargs: object) -> None:
            observed_transaction_state.append(conn.in_transaction)
            raise RuntimeError("audit unavailable")

        self.audit_required.side_effect = fail_audit
        with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
            await self._provision(pool)

        self.assertEqual(observed_transaction_state, [True])
        self.assertEqual(pool.store.provisions, {})
        self.assertEqual(pool.store.tenants, {})
        self.assertEqual(pool.store.service_accounts, {})
        self.assertEqual(pool.store.tenant_sequence, 0)
        self.assertEqual(pool.store.service_account_sequence, 0)


class TestPartnerProvisionSchema(unittest.IsolatedAsyncioTestCase):
    async def test_production_asserts_schema_without_runtime_ddl(self) -> None:
        pool = AsyncMock()
        with (
            patch.object(
                provision_svc.tenant_svc,
                "ensure_secure_schema",
                new=AsyncMock(),
            ) as ensure_secure,
            patch.object(provision_svc.sa_svc, "ensure_schema", new=AsyncMock()) as ensure_sa,
            patch.object(
                provision_svc.audit,
                "ensure_audit_schema",
                new=AsyncMock(),
            ) as ensure_audit,
            patch.object(provision_svc.settings, "SOFT_MIGRATE_SCHEMA", False),
        ):
            await provision_svc.ensure_partner_provision_schema(pool)

        ensure_secure.assert_awaited_once_with(pool)
        ensure_sa.assert_not_awaited()
        ensure_audit.assert_not_awaited()
        pool.execute.assert_not_awaited()

    async def test_soft_schema_prepares_required_audit_table(self) -> None:
        pool = AsyncMock()
        with (
            patch.object(provision_svc.tenant_svc, "ensure_secure_schema", new=AsyncMock()),
            patch.object(provision_svc.sa_svc, "ensure_schema", new=AsyncMock()),
            patch.object(
                provision_svc.audit, "ensure_audit_schema", new=AsyncMock()
            ) as ensure_audit,
            patch.object(
                provision_svc.settings,
                "SOFT_MIGRATE_SCHEMA",
                True,
            ),
        ):
            await provision_svc.ensure_partner_provision_schema(pool)

        ensure_audit.assert_awaited_once_with(pool)


if __name__ == "__main__":
    unittest.main()
