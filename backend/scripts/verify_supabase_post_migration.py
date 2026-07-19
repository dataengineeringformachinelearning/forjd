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
import os
import sys
from typing import Any


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
    "status_pages",
    "service_accounts",
    "embedding_vectors",
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
      # Optional — 015 may add them when publication exists
      results.append(
        (f"realtime_{rel}", True, "published" if in_pub else "not_in_publication")
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
    "publication_supabase_realtime",
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
