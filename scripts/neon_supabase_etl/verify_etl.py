#!/usr/bin/env python3
"""Post-migration verification for Neon → Supabase ETL.

  cd backend && uv run --group etl python ../scripts/neon_supabase_etl/verify_etl.py \\
    --config ../scripts/neon_supabase_etl/config.local.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from forjd_etl.config import load_config  # noqa: E402
from forjd_etl.db import connect, resolve_source_dsn, resolve_target_dsn  # noqa: E402
from forjd_etl.verify import print_report, verify_migration  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verify Neon → Supabase ETL results")
    p.add_argument("--config", required=True, type=Path)
    p.add_argument("--table", action="append", default=[])
    p.add_argument("--mode", choices=("full", "incremental"), default=None)
    p.add_argument("--tenant-id", default=None)
    p.add_argument("-v", "--verbose", action="count", default=0)
    args = p.parse_args(argv)

    level = (
        logging.WARNING
        if args.verbose == 0
        else (logging.INFO if args.verbose == 1 else logging.DEBUG)
    )
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")

    cfg = load_config(args.config)
    if args.mode:
        cfg.mode = args.mode
    if args.tenant_id:
        cfg.params["tenant_id"] = args.tenant_id

    only = {t.strip() for t in args.table if t.strip()}
    specs = [t for t in cfg.tables if t.enabled and (not only or t.source in only)]

    with connect(resolve_source_dsn()) as source, connect(resolve_target_dsn()) as target:
        results = verify_migration(source=source, target=target, cfg=cfg, tables=specs)
    return 1 if print_report(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
