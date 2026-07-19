#!/usr/bin/env python3
"""Controlled Neon → Supabase ETL (schema + data + transforms).

Usage (from repo, with backend uv env):

  cd backend && uv sync --group etl
  export NEON_DATABASE_URL='postgresql://…@….neon.tech/…?sslmode=require'
  export SUPABASE_DATABASE_URL='postgresql://postgres.…@db.…supabase.co:5432/postgres'
  uv run --group etl python ../scripts/neon_supabase_etl/neon_to_supabase.py \\
    --config ../scripts/neon_supabase_etl/config.local.yaml

See docs/NEON_TO_SUPABASE_ETL.md.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow `python neon_to_supabase.py` without installing the package.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from forjd_etl import schema as schema_svc  # noqa: E402
from forjd_etl import state as state_svc  # noqa: E402
from forjd_etl.config import load_config  # noqa: E402
from forjd_etl.db import (  # noqa: E402
    connect,
    redacted_dsn_label,
    resolve_source_dsn,
    resolve_target_dsn,
)
from forjd_etl.transfer import migrate_table  # noqa: E402


# --- CLI ---
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Neon → Supabase controlled ETL (idempotent, resumable)"
    )
    p.add_argument(
        "--config",
        required=True,
        type=Path,
        help="YAML config (copy from config.example.yaml)",
    )
    p.add_argument(
        "--mode",
        choices=("full", "incremental"),
        default=None,
        help="Override options.mode",
    )
    p.add_argument(
        "--table",
        action="append",
        default=[],
        help="Only migrate these source table names (repeatable)",
    )
    p.add_argument("--dry-run", action="store_true", help="Fetch + transform; no writes")
    p.add_argument(
        "--reset",
        action="store_true",
        help="Clear checkpoint for selected tables before run",
    )
    p.add_argument("--since", default=None, help="Bind param since (ISO timestamp)")
    p.add_argument("--until", default=None, help="Bind param until (ISO timestamp)")
    p.add_argument("--tenant-id", default=None, help="Bind param tenant_id (UUID)")
    p.add_argument("--batch-size", type=int, default=None, help="Override batch size")
    p.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (-v INFO, -vv DEBUG)",
    )
    return p


def configure_logging(verbose: int) -> None:
    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)
    log = logging.getLogger("forjd.etl")

    cfg = load_config(args.config)
    if args.mode:
        cfg.mode = args.mode
    if args.dry_run:
        cfg.dry_run = True
    if args.batch_size is not None:
        cfg.batch_size = max(1, args.batch_size)
    if args.since:
        cfg.params["since"] = args.since
    if args.until:
        cfg.params["until"] = args.until
    if args.tenant_id:
        cfg.params["tenant_id"] = args.tenant_id

    only = {t.strip() for t in args.table if t.strip()}
    specs = [t for t in cfg.tables if t.enabled and (not only or t.source in only)]
    if only:
        missing = only - {t.source for t in cfg.tables}
        if missing:
            log.error("unknown --table names: %s", ", ".join(sorted(missing)))
            return 2
        if not specs:
            log.error("no enabled tables matched --table filters")
            return 2

    source_dsn = resolve_source_dsn()
    target_dsn = resolve_target_dsn()
    log.info("source=%s", redacted_dsn_label(source_dsn))
    log.info("target=%s", redacted_dsn_label(target_dsn))
    log.info(
        "mode=%s dry_run=%s tables=%s",
        cfg.mode,
        cfg.dry_run,
        [t.source for t in specs],
    )

    summaries: list[dict] = []
    with connect(source_dsn) as source, connect(target_dsn) as target:
        if not cfg.dry_run:
            schema_svc.ensure_extensions(target, cfg.extensions)
            if cfg.create_schema:
                schema_svc.ensure_schema(target, cfg.target_schema)
            state_svc.ensure_state_table(target, cfg.target_schema, cfg.state_table)
            target.commit()

        for spec in specs:
            try:
                summary = migrate_table(
                    source=source,
                    target=target,
                    cfg=cfg,
                    spec=spec,
                    reset=args.reset,
                )
                summaries.append(summary)
            except Exception as exc:  # noqa: BLE001
                log.exception("table %s failed: %s", spec.source, exc)
                if not cfg.dry_run:
                    key = state_svc.table_key(
                        cfg.source_schema,
                        spec.source,
                        cfg.target_schema,
                        spec.target,
                    )
                    state_svc.upsert_checkpoint(
                        target,
                        schema=cfg.target_schema,
                        state_table=cfg.state_table,
                        key=key,
                        source_table=spec.source,
                        target_table=spec.target,
                        mode=cfg.mode,
                        watermark=None,
                        rows_upserted=0,
                        status="failed",
                        last_error=str(exc)[:2000],
                    )
                    target.commit()
                summaries.append(
                    {
                        "table": spec.source,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                return 1

    print("\n--- ETL summary ---")
    for s in summaries:
        print(
            f"{s.get('status', '?'):20} {s.get('table')} "
            f"rows={s.get('rows', '-')} watermark={s.get('watermark')}"
        )
    failed = [s for s in summaries if s.get("status") == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
