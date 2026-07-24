"""Database contract tests for tenant-bound status children."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestStatusTenantIntegrityMigration(unittest.TestCase):
    def test_migration_preflights_and_enforces_composite_parent_keys(self) -> None:
        sql = (ROOT / "sql/028_status_child_tenant_integrity.sql").read_text()
        for marker in (
            "health_probe_observations_service_observed_idx",
            "(service_id, observed_at DESC)",
            "INCLUDE (is_active)",
            "status_pages_id_tenant_key",
            "status_services_id_tenant_key",
            "status_services contains a page_id/tenant_id mismatch",
            "status_incidents contains a page_id/tenant_id mismatch",
            "health_probe_observations contains a service_id/tenant_id mismatch",
            "FOREIGN KEY (page_id, tenant_id)",
            "REFERENCES public.status_pages (id, tenant_id)",
            "FOREIGN KEY (service_id, tenant_id)",
            "REFERENCES public.status_services (id, tenant_id)",
            "VALIDATE CONSTRAINT status_services_page_tenant_fkey",
            "VALIDATE CONSTRAINT status_incidents_page_tenant_fkey",
            "VALIDATE CONSTRAINT health_probe_observations_service_tenant_fkey",
            "pg_get_indexdef",
            "unexpected definition",
        ):
            self.assertIn(marker, sql)
        self.assertLess(
            sql.index("VALIDATE CONSTRAINT status_services_page_tenant_fkey"),
            sql.index("DROP CONSTRAINT IF EXISTS status_services_page_id_fkey"),
        )
        self.assertLess(
            sql.index("VALIDATE CONSTRAINT status_incidents_page_tenant_fkey"),
            sql.index("DROP CONSTRAINT IF EXISTS status_incidents_page_id_fkey"),
        )
        self.assertLess(
            sql.index("VALIDATE CONSTRAINT health_probe_observations_service_tenant_fkey"),
            sql.index("DROP CONSTRAINT IF EXISTS health_probe_observations_service_id_fkey"),
        )

    def test_migrations_are_contiguous_through_status_integrity(self) -> None:
        versions = sorted(
            int(path.name.split("_", 1)[0]) for path in (ROOT / "sql").glob("[0-9][0-9][0-9]_*.sql")
        )
        self.assertEqual(versions, list(range(3, 29)))

    def test_post_migration_verifier_requires_validated_constraints(self) -> None:
        verifier = (ROOT / "scripts/verify_supabase_post_migration.py").read_text()
        for constraint in (
            "health_probe_observations_service_observed_idx",
            "status_pages_id_tenant_key",
            "status_services_id_tenant_key",
            "status_services_page_tenant_fkey",
            "status_incidents_page_tenant_fkey",
            "health_probe_observations_service_tenant_fkey",
            "contract_status_service_tenant_mismatch",
            "contract_status_incident_tenant_mismatch",
            "contract_health_probe_tenant_mismatch",
            "pg_get_indexdef",
        ):
            self.assertIn(constraint, verifier)
        self.assertIn("c.convalidated", verifier)
        self.assertIn("c.contype", verifier)
        self.assertIn('"constraint_",', verifier)
        self.assertIn('"contract_",', verifier)


if __name__ == "__main__":
    unittest.main()
