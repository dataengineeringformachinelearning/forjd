#!/usr/bin/env python3
"""Apply ordered FORJD SQL migrations atomically; never print the DSN."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import re
import sys
from pathlib import Path

import asyncpg

# Prefer /app/sql on Fly images; fall back to repo layout next to this script.
_CANDIDATES = (
    Path(os.environ.get("FORJD_SQL_DIR", "")),
    Path("/app/sql"),
    Path(__file__).resolve().parents[1] / "sql",
    Path.cwd() / "sql",
)
SQL_DIR = next(
    (p for p in _CANDIDATES if p and (p / "003_secure_tenancy.sql").is_file()),
    Path("/app/sql"),
)

_MIGRATION_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")

NEEDED = [
    "aggregated_analytics",
    "assets",
    "audit_events",
    "crypto_sessions",
    "correlation_receipts",
    "daemon_api_keys",
    "discovered_endpoints",
    "embedding_vectors",
    "endpoint_observations",
    "export_jobs",
    "health_probe_observations",
    "honeypot_endpoints",
    "honeypot_interactions",
    "incident_cases",
    "ingest_processing_batches",
    "lighthouse_scans",
    "ml_scores",
    "outbox_events",
    "partner_provisions",
    "playbook_action_results",
    "playbook_actions",
    "playbook_runs",
    "playbooks",
    "projection_checkpoints",
    "projection_dlq",
    "report_archives",
    "report_documents",
    "scheduled_task_runs",
    "security_signals",
    "service_accounts",
    "status_incidents",
    "status_pages",
    "status_services",
    "stream_results",
    "telemetry_events",
    "telemetry_ingest_receipts",
    "tenant_erase_receipts",
    "tenant_members",
    "tenants",
    "threat_intelligence",
    "threat_reports",
    "training_runs",
    "use_cases",
    "validated_sites",
    "vulnerabilities",
    "web_technology_observations",
    "forjd_schema_migrations",
]
RLS_NEEDED = [table for table in NEEDED if table != "forjd_schema_migrations"]


def _normalize_dsn(raw: str) -> str:
    dsn = raw.strip()
    if dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + dsn.removeprefix("postgresql+asyncpg://")
    return dsn


def _migration_files() -> list[tuple[int, Path]]:
    found: dict[int, Path] = {}
    for path in SQL_DIR.glob("*.sql"):
        match = _MIGRATION_RE.fullmatch(path.name)
        if not match:
            continue
        version = int(match.group(1))
        if version < 3:
            continue
        if version in found:
            raise RuntimeError(f"duplicate migration version {version:03d}")
        found[version] = path
    if not found:
        raise RuntimeError(f"no migrations found in {SQL_DIR}")
    latest = max(found)
    missing = [version for version in range(3, latest + 1) if version not in found]
    if missing:
        versions = ", ".join(f"{version:03d}" for version in missing)
        raise RuntimeError(f"migration sequence has gaps: {versions}")
    return sorted(found.items())


async def main() -> int:
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("POSTGRES_DSN missing", file=sys.stderr)
        return 2

    try:
        files = _migration_files()
    except RuntimeError as exc:
        print(f"migration discovery failed: {exc}", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(_normalize_dsn(dsn))
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS public.forjd_schema_migrations (
                version INT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                checksum_sha256 TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.fetchval(
            "SELECT pg_advisory_lock(hashtextextended('forjd-schema-migrations', 0))"
        )

        local_versions = {version for version, _ in files}
        applied_versions = {
            int(row["version"])
            for row in await conn.fetch(
                """
                SELECT version
                FROM public.forjd_schema_migrations
                WHERE version >= 3
                """
            )
        }
        unknown_versions = sorted(applied_versions - local_versions)
        if unknown_versions:
            versions = ", ".join(f"{version:03d}" for version in unknown_versions)
            print(
                "ERROR database contains migration version(s) newer than or "
                f"unknown to this checkout: {versions}",
                file=sys.stderr,
            )
            return 1

        for version, path in files:
            name = path.name
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            applied = await conn.fetchrow(
                """
                SELECT name, checksum_sha256
                FROM public.forjd_schema_migrations
                WHERE version = $1
                """,
                version,
            )
            if applied is not None:
                if applied["name"] != name or applied["checksum_sha256"] != checksum:
                    print(
                        f"ERROR migration {version:03d} checksum/name drift: {name}",
                        file=sys.stderr,
                    )
                    return 1
                print(f"SKIP  {name} (already applied, checksum ok)")
                continue

            print(f"APPLY {name} ({len(sql)} bytes)...")
            try:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        """
                        INSERT INTO public.forjd_schema_migrations (
                            version, name, checksum_sha256
                        ) VALUES ($1, $2, $3)
                        """,
                        version,
                        name,
                        checksum,
                    )
                print(f"OK    {name}")
            except Exception as exc:  # noqa: BLE001 — fail fast without leaking DSN
                msg = str(exc).splitlines()[0][:240]
                print(f"ERROR {name}: {msg}", file=sys.stderr)
                return 1

        missing: list[str] = []
        for table in NEEDED:
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.tables
                  WHERE table_schema = 'public' AND table_name = $1
                )
                """,
                table,
            )
            if not exists:
                missing.append(table)
        if missing:
            print("still missing: " + ", ".join(missing), file=sys.stderr)
            return 1
        no_rls: list[str] = []
        for table in RLS_NEEDED:
            enabled = await conn.fetchval(
                """
                SELECT c.relrowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = $1
                """,
                table,
            )
            if not enabled:
                no_rls.append(table)
        if no_rls:
            print("RLS disabled: " + ", ".join(no_rls), file=sys.stderr)
            return 1
        print("SCHEMA_OK")
        return 0
    finally:
        with contextlib.suppress(Exception):
            await conn.fetchval(
                "SELECT pg_advisory_unlock(hashtextextended('forjd-schema-migrations', 0))"
            )
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
