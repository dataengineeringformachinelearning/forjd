#!/usr/bin/env python3
"""Post-migration checks for FORJD Supabase Postgres (RLS, pgvector, Realtime).

Never prints connection strings. Exit 0 = all required gates pass.

Usage:
  POSTGRES_DSN='postgresql://…' python scripts/verify_supabase_post_migration.py
  # or on Fly:
  fly ssh console -a forjd-backend -C \
    'sh -c "cd /app && .venv/bin/python scripts/verify_supabase_post_migration.py"'
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any

_MIGRATION_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
_SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def _normalize_dsn(raw: str) -> str:
    dsn = raw.strip()
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = "postgresql://" + dsn.removeprefix("postgresql+asyncpg://")
    return dsn


async def _check(conn: Any) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    version = await conn.fetchval("SELECT version()")
    results.append(("postgres_version", True, str(version).split(",")[0]))

    # --- Extensions ---
    exts = {
        r["extname"]: r["extversion"]
        for r in await conn.fetch("SELECT extname, extversion FROM pg_extension")
    }
    for name in ("pgcrypto", "vector"):
        ok = name in exts
        results.append((f"extension_{name}", ok, exts.get(name, "MISSING")))

    # --- Core FORJD tables ---
    needed = (
        "tenants",
        "tenant_members",
        "telemetry_events",
        "crypto_sessions",
        "stream_results",
        "projection_checkpoints",
        "projection_dlq",
        "status_incidents",
        "status_pages",
        "status_services",
        "health_probe_observations",
        "service_accounts",
        "embedding_vectors",
        "security_signals",
        "correlation_receipts",
        "playbook_runs",
        "playbook_action_results",
        "tenant_erase_receipts",
        "ingest_processing_batches",
        "partner_provisions",
        "forjd_schema_migrations",
    )
    for table in needed:
        exists = await conn.fetchval(
            """
      SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = $1
      )
      """,
            table,
        )
        results.append((f"table_{table}", bool(exists), "ok" if exists else "MISSING"))

    # --- RLS enabled on sensitive tables ---
    rls_tables = (
        "tenants",
        "tenant_members",
        "telemetry_events",
        "stream_results",
        "crypto_sessions",
        "service_accounts",
        "embedding_vectors",
        "projection_checkpoints",
        "projection_dlq",
        "status_incidents",
        "status_pages",
        "status_services",
        "health_probe_observations",
        "security_signals",
        "correlation_receipts",
        "playbook_runs",
        "playbook_action_results",
        "tenant_erase_receipts",
        "ingest_processing_batches",
        "partner_provisions",
    )
    for table in rls_tables:
        enabled = await conn.fetchval(
            """
      SELECT c.relrowsecurity
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relname = $1 AND c.relkind = 'r'
      """,
            table,
        )
        results.append((f"rls_{table}", bool(enabled), "on" if enabled else "OFF"))
        if enabled:
            policies = await conn.fetchval(
                """
                SELECT COUNT(*) FROM pg_policies
                WHERE schemaname = 'public' AND tablename = $1
                """,
                table,
            )
            results.append(
                (
                    f"policy_{table}",
                    bool(policies),
                    f"{int(policies or 0)} policy(s)",
                )
            )

    # --- Reliability columns and indexes introduced by migrations 021-025 ---
    required_columns = {
        "telemetry_events": ("ciphertext_bytes", "ingest_fingerprint"),
        "stream_results": ("projection_result_key", "projection_version"),
        "projection_dlq": (
            "dedupe_key",
            "projection_version",
            "next_attempt_at",
            "locked_by",
            "lease_expires_at",
            "max_attempts",
        ),
        "tenant_erase_receipts": (
            "erased_credential_prefix",
            "erased_credential_hash",
        ),
        "ingest_processing_batches": (
            "workflow_hash",
            "workflow_snapshot",
            "event_ids",
            "tenant_ids",
            "status",
            "lease_owner",
            "lease_expires_at",
        ),
        "security_signals": (
            "processing_status",
            "processing_result",
            "processing_completed_at",
        ),
        "correlation_receipts": ("result_snapshot",),
        "playbook_action_results": ("configuration_snapshot",),
    }
    for table, columns in required_columns.items():
        for column in columns:
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'public'
                    AND table_name = $1
                    AND column_name = $2
                )
                """,
                table,
                column,
            )
            results.append(
                (
                    f"column_{table}_{column}",
                    bool(exists),
                    "ok" if exists else "MISSING",
                )
            )

    required_indexes = (
        "stream_results_projection_result_uidx",
        "projection_dlq_open_dedupe_uidx",
        "telemetry_events_projector_cursor_idx",
        "tenant_erase_receipts_credential_hash_uidx",
        "ingest_processing_worker_idx",
        "ingest_processing_event_ids_gin_idx",
        "export_jobs_tenant_idempotency_idx",
        "export_jobs_worker_idx",
        "export_jobs_expiry_idx",
        "export_jobs_artifact_cleanup_idx",
        "security_signals_processing_idx",
        "playbook_runs_continuation_ready_idx",
        "partner_provisions_partner_external_ref_uidx",
        "partner_provisions_tenant_uidx",
        "partner_provisions_service_account_uidx",
        "service_accounts_id_tenant_uidx",
        "health_probe_observations_service_observed_idx",
    )
    index_contracts = {
        "partner_provisions_partner_external_ref_uidx": (
            "partner_provisions",
            ("partner", "external_ref"),
            2,
            True,
        ),
        "partner_provisions_tenant_uidx": (
            "partner_provisions",
            ("tenant_id",),
            1,
            True,
        ),
        "partner_provisions_service_account_uidx": (
            "partner_provisions",
            ("service_account_id",),
            1,
            True,
        ),
        "service_accounts_id_tenant_uidx": (
            "service_accounts",
            ("id", "tenant_id"),
            2,
            True,
        ),
        "health_probe_observations_service_observed_idx": (
            "health_probe_observations",
            ("service_id", "observed_at DESC", "is_active"),
            2,
            False,
        ),
    }
    for index in required_indexes:
        if contract := index_contracts.get(index):
            table, columns, key_columns, unique = contract
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM pg_index i
                  JOIN pg_class c ON c.oid = i.indexrelid
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'public'
                    AND c.relname = $1
                    AND i.indrelid = ('public.' || $2)::regclass
                    AND i.indisunique = $3
                    AND i.indisvalid
                    AND i.indisready
                    AND i.indpred IS NULL
                    AND i.indexprs IS NULL
                    AND i.indnkeyatts = $4
                    AND i.indnatts = CARDINALITY($5::text[])
                    AND ARRAY(
                      SELECT pg_get_indexdef(i.indexrelid, ordinal, FALSE)
                      FROM generate_series(1, i.indnatts) AS ordinal
                      ORDER BY ordinal
                    ) = $5::text[]
                )
                """,
                index,
                table,
                unique,
                key_columns,
                list(columns),
            )
        else:
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                  SELECT 1 FROM pg_indexes
                  WHERE schemaname = 'public' AND indexname = $1
                )
                """,
                index,
            )
        results.append((f"index_{index}", bool(exists), "ok" if exists else "MISSING"))

    for trigger in (
        "ingest_processing_identity_immutable",
        "ingest_processing_tenant_integrity",
    ):
        exists = await conn.fetchval(
            """
            SELECT EXISTS (
              SELECT 1
              FROM pg_trigger t
              JOIN pg_class c ON c.oid = t.tgrelid
              JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public'
                AND c.relname = 'ingest_processing_batches'
                AND t.tgname = $1
                AND NOT t.tgisinternal
            )
            """,
            trigger,
        )
        results.append(
            (
                f"trigger_{trigger}",
                bool(exists),
                "ok" if exists else "MISSING",
            )
        )

    for table, constraint, constraint_type in (
        ("service_accounts", "service_accounts_auth_or_opaque", "c"),
        ("partner_provisions", "partner_provisions_partner_format", "c"),
        ("partner_provisions", "partner_provisions_service_account_tenant_fkey", "f"),
        ("status_pages", "status_pages_id_tenant_key", "u"),
        ("status_services", "status_services_id_tenant_key", "u"),
        ("status_services", "status_services_page_tenant_fkey", "f"),
        ("status_incidents", "status_incidents_page_tenant_fkey", "f"),
        (
            "health_probe_observations",
            "health_probe_observations_service_tenant_fkey",
            "f",
        ),
    ):
        exists = await conn.fetchval(
            """
            SELECT EXISTS (
              SELECT 1
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
              WHERE n.nspname = 'public'
                AND t.relname = $1
                AND c.conname = $2
                AND c.contype = $3::"char"
                AND c.convalidated
            )
            """,
            table,
            constraint,
            constraint_type,
        )
        results.append(
            (
                f"constraint_{constraint}",
                bool(exists),
                "validated" if exists else "MISSING",
            )
        )

    # --- Cross-table tenant and provision data contracts ---
    contract_queries = (
        (
            "contract_partner_provision_duplicates",
            """
            SELECT COUNT(*)
            FROM (
              SELECT partner, external_ref
              FROM public.partner_provisions
              GROUP BY partner, external_ref
              HAVING COUNT(*) > 1
            ) AS duplicates
            """,
        ),
        (
            "contract_partner_provision_tenant_mismatch",
            """
            SELECT COUNT(*)
            FROM public.partner_provisions AS provision
            LEFT JOIN public.service_accounts AS account
              ON account.id = provision.service_account_id
             AND account.tenant_id = provision.tenant_id
            WHERE account.id IS NULL
            """,
        ),
        (
            "contract_partner_provision_tenant_aliases",
            """
            SELECT COUNT(*)
            FROM (
              SELECT tenant_id
              FROM public.partner_provisions
              GROUP BY tenant_id
              HAVING COUNT(*) > 1
            ) AS aliases
            """,
        ),
        (
            "contract_partner_provision_credential_aliases",
            """
            SELECT COUNT(*)
            FROM (
              SELECT service_account_id
              FROM public.partner_provisions
              GROUP BY service_account_id
              HAVING COUNT(*) > 1
            ) AS aliases
            """,
        ),
        (
            "contract_status_service_tenant_mismatch",
            """
            SELECT COUNT(*)
            FROM public.status_services AS child
            LEFT JOIN public.status_pages AS parent
              ON parent.id = child.page_id
             AND parent.tenant_id = child.tenant_id
            WHERE parent.id IS NULL
            """,
        ),
        (
            "contract_status_incident_tenant_mismatch",
            """
            SELECT COUNT(*)
            FROM public.status_incidents AS child
            LEFT JOIN public.status_pages AS parent
              ON parent.id = child.page_id
             AND parent.tenant_id = child.tenant_id
            WHERE parent.id IS NULL
            """,
        ),
        (
            "contract_health_probe_tenant_mismatch",
            """
            SELECT COUNT(*)
            FROM public.health_probe_observations AS child
            LEFT JOIN public.status_services AS parent
              ON parent.id = child.service_id
             AND parent.tenant_id = child.tenant_id
            WHERE parent.id IS NULL
            """,
        ),
        (
            "contract_active_deml_ml_write",
            """
            SELECT COUNT(*)
            FROM public.service_accounts AS account
            WHERE account.is_active
              AND account.revoked_at IS NULL
              AND NOT ('ml:write' = ANY(account.scopes))
              AND (
                LOWER(BTRIM(COALESCE(account.subprocessor, ''))) = 'deml'
                OR EXISTS (
                  SELECT 1
                  FROM public.partner_provisions AS provision
                  WHERE provision.service_account_id = account.id
                    AND LOWER(BTRIM(provision.partner)) = 'deml'
                )
              )
            """,
        ),
    )
    for name, query in contract_queries:
        violations = int(await conn.fetchval(query) or 0)
        results.append(
            (
                name,
                violations == 0,
                "ok" if violations == 0 else f"{violations} violation(s)",
            )
        )

    # --- Migration ledger: every local migration must match its applied checksum ---
    migration_paths: dict[int, Path] = {}
    for path in _SQL_DIR.glob("*.sql"):
        match = _MIGRATION_RE.fullmatch(path.name)
        if match and int(match.group(1)) >= 3:
            migration_paths[int(match.group(1))] = path
    ledger_errors: list[str] = []
    ledger_exists = await conn.fetchval(
        "SELECT to_regclass('public.forjd_schema_migrations') IS NOT NULL"
    )
    if ledger_exists:
        applied_rows = await conn.fetch(
            """
            SELECT version, name, checksum_sha256
            FROM public.forjd_schema_migrations
            WHERE version >= 3
            ORDER BY version
            """
        )
        applied = {int(row["version"]): row for row in applied_rows}
        for version in sorted(set(applied) - set(migration_paths)):
            ledger_errors.append(f"{version:03d}:unknown")
        for version, path in sorted(migration_paths.items()):
            row = applied.get(version)
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            if row is None:
                ledger_errors.append(f"{version:03d}:missing")
            elif row["name"] != path.name or row["checksum_sha256"] != checksum:
                ledger_errors.append(f"{version:03d}:drift")
    else:
        ledger_errors.append("table:missing")
    results.append(
        (
            "migration_ledger",
            not ledger_errors and bool(migration_paths),
            "ok" if not ledger_errors else ", ".join(ledger_errors),
        )
    )

    # --- Realtime publication ---
    pub = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime')"
    )
    results.append(("publication_supabase_realtime", bool(pub), "ok" if pub else "MISSING"))

    if pub:
        for rel in ("stream_results", "telemetry_events"):
            in_pub = await conn.fetchval(
                """
        SELECT EXISTS (
          SELECT 1
          FROM pg_publication_rel pr
          JOIN pg_publication p ON p.oid = pr.prpubid
          JOIN pg_class c ON c.oid = pr.prrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
          WHERE p.pubname = 'supabase_realtime'
            AND n.nspname = 'public'
            AND c.relname = $1
        )
        """,
                rel,
            )
            results.append(
                (
                    f"realtime_{rel}",
                    bool(in_pub),
                    "published" if in_pub else "not_in_publication",
                )
            )

    # --- Views ---
    for view in ("projection_feed", "sealed_events"):
        exists = await conn.fetchval(
            """
      SELECT EXISTS (
        SELECT 1 FROM information_schema.views
        WHERE table_schema = 'public' AND table_name = $1
      )
      """,
            view,
        )
        results.append((f"view_{view}", bool(exists), "ok" if exists else "MISSING"))

    # --- Optional partner control-plane schema (PARTNER_CONTROL_SCHEMA) ---
    partner_schema = (os.environ.get("PARTNER_CONTROL_SCHEMA") or "").strip()
    if partner_schema:
        present = await conn.fetchval(
            """
      SELECT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = $1
      )
      """,
            partner_schema,
        )
        results.append(
            (
                f"schema_{partner_schema}_optional",
                True,
                "present" if present else "absent",
            )
        )

    return results


async def main() -> int:
    raw = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL") or ""
    if not raw.strip():
        print("POSTGRES_DSN / DATABASE_URL missing", file=sys.stderr)
        return 2

    try:
        import asyncpg
    except ImportError:
        print("asyncpg required", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(_normalize_dsn(raw))
    try:
        results = await _check(conn)
    finally:
        await conn.close()

    required_prefixes = (
        "extension_",
        "table_",
        "rls_",
        "policy_",
        "column_",
        "index_",
        "constraint_",
        "contract_",
        "migration_ledger",
        "publication_supabase_realtime",
        "realtime_",
        "view_",
    )
    failed = 0
    for name, ok, detail in results:
        mark = "OK  " if ok else "FAIL"
        print(f"{mark}  {name}: {detail}")
        if not ok and name.startswith(required_prefixes):
            failed += 1

    if failed:
        print(f"\n{failed} required check(s) failed", file=sys.stderr)
        return 1
    print("\nAll required post-migration checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
