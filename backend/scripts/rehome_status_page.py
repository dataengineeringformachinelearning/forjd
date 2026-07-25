#!/usr/bin/env python3
"""Move a status page onto a different FORJD tenant (ops tool).

Use when a customer page (e.g. joealongi-dev) was accidentally created under the
DEML platform tenant and must keep unique analytics/ML stats.

Does **not** migrate stream_results / training_runs / aggregated_analytics —
those remain on the source tenant. After rehome, new probes/widget/heartbeat
traffic for the page must use the target tenant credential.

Examples
--------
  DATABASE_URL=… python scripts/rehome_status_page.py \\
    --slug joealongi-dev \\
    --target-tenant-id 33333333-3333-3333-3333-333333333333

  DATABASE_URL=… python scripts/rehome_status_page.py \\
    --slug joealongi-dev \\
    --target-tenant-slug joealongi \\
    --create-tenant-name "joealongi.dev"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

# Allow `python scripts/rehome_status_page.py` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def _run(args: argparse.Namespace) -> int:
    import asyncpg

    from app.services import status as status_svc

    dsn = (
        args.database_url
        or os.environ.get("DATABASE_URL")
        or os.environ.get("SUPABASE_DB_URL")
        or ""
    ).strip()
    if not dsn:
        print("DATABASE_URL (or --database-url) is required", file=sys.stderr)
        return 2

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    assert pool is not None
    try:
        target_tenant_id: UUID
        if args.target_tenant_id:
            target_tenant_id = UUID(args.target_tenant_id)
        elif args.target_tenant_slug:
            slug = args.target_tenant_slug.strip().lower()
            row = await pool.fetchrow(
                "SELECT id::text FROM tenants WHERE slug = $1",
                slug,
            )
            if row is None:
                if not args.create_tenant_name:
                    print(
                        f"tenant slug {slug!r} not found; pass --create-tenant-name to create",
                        file=sys.stderr,
                    )
                    return 1
                # Ops path: create tenant shell without requiring a human owner JWT.
                created = await pool.fetchrow(
                    """
                    INSERT INTO tenants (slug, name)
                    VALUES ($1, $2)
                    RETURNING id::text, slug, name
                    """,
                    slug,
                    args.create_tenant_name,
                )
                target_tenant_id = UUID(str(created["id"]))
                print(f"created tenant {slug} id={target_tenant_id}")
            else:
                target_tenant_id = UUID(str(row["id"]))
        else:
            print("pass --target-tenant-id or --target-tenant-slug", file=sys.stderr)
            return 2

        result = await status_svc.rehome_status_page(
            pool,
            slug=args.slug.strip().lower(),
            target_tenant_id=target_tenant_id,
        )
        print(result)
        return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True, help="Status page slug to move")
    parser.add_argument("--target-tenant-id", default="", help="Destination tenant UUID")
    parser.add_argument(
        "--target-tenant-slug",
        default="",
        help="Destination tenant slug (lookup or create with --create-tenant-name)",
    )
    parser.add_argument(
        "--create-tenant-name",
        default="",
        help="When target slug is missing, create tenant with this display name",
    )
    parser.add_argument("--database-url", default="", help="Postgres DSN override")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
