#!/usr/bin/env python3
"""Apply backend/sql/003–017 in order (idempotent-ish; prints status, never the DSN)."""

from __future__ import annotations

import asyncio
import os
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
SQL_DIR = next((p for p in _CANDIDATES if p and (p / "003_secure_tenancy.sql").is_file()), Path("/app/sql"))

FILES = [
    "003_secure_tenancy.sql",
    "004_crypto_sessions.sql",
    "005_stream_results.sql",
    "006_universal_stream.sql",
    "007_projections.sql",
    "008_status_pages.sql",
    "009_daemon_data_plane.sql",
    "010_audit_and_rate_limits.sql",
    "011_domain_security.sql",
    "012_domain_scanners.sql",
    "013_e2ee_hardening.sql",
    "014_service_accounts.sql",
    "015_realtime_and_consumer.sql",
    "016_ml_supabase.sql",
    "017_service_principal_cutover.sql",
]

NEEDED = [
    "tenants",
    "tenant_members",
    "telemetry_events",
    "crypto_sessions",
    "stream_results",
    "projection_checkpoints",
    "projection_dlq",
    "status_pages",
    "service_accounts",
]


async def main() -> int:
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("POSTGRES_DSN missing", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(dsn)
    try:
        for name in FILES:
            path = SQL_DIR / name
            if not path.is_file():
                print(f"SKIP missing {name}")
                continue
            sql = path.read_text(encoding="utf-8")
            print(f"APPLY {name} ({len(sql)} bytes)...")
            try:
                await conn.execute(sql)
                print(f"OK    {name}")
            except Exception as exc:  # noqa: BLE001 — report and continue for re-runs
                msg = str(exc).splitlines()[0][:240]
                print(f"WARN  {name}: {msg}")

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
        print("SCHEMA_OK")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
