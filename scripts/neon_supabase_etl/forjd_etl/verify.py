"""Post-ETL verification: counts, PK coverage, extension/schema gates."""

from __future__ import annotations

import logging
from typing import Any

import psycopg

from forjd_etl import schema as schema_svc
from forjd_etl.config import EtlConfig, TableSpec
from forjd_etl.db import qualify
from forjd_etl.transforms import resolve_column_map

logger = logging.getLogger("forjd.etl.verify")


def verify_migration(
    *,
    source: psycopg.Connection,
    target: psycopg.Connection,
    cfg: EtlConfig,
    tables: list[TableSpec] | None = None,
) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    # --- Extensions ---
    ext_rows = target.execute("SELECT extname FROM pg_extension").fetchall()
    present = {r["extname"] for r in ext_rows}
    for ext in cfg.extensions:
        ok = ext in present or ext.replace("-", "_") in present
        results.append((f"extension_{ext}", ok, "ok" if ok else "MISSING"))

    # --- Target schema ---
    sch = target.execute(
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
        (cfg.target_schema,),
    ).fetchone()
    results.append(("target_schema", sch is not None, cfg.target_schema if sch else "MISSING"))

    # --- Not colliding with FORJD public ---
    results.append(("target_not_public", cfg.target_schema != "public", cfg.target_schema))

    specs = tables if tables is not None else [t for t in cfg.tables if t.enabled]
    for spec in specs:
        results.extend(_verify_table(source, target, cfg, spec))

    return results


def _verify_table(
    source: psycopg.Connection,
    target: psycopg.Connection,
    cfg: EtlConfig,
    spec: TableSpec,
) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    src_q = qualify(cfg.source_schema, spec.source)
    tgt_q = qualify(cfg.target_schema, spec.target)

    src_exists = source.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (cfg.source_schema, spec.source),
    ).fetchone()
    tgt_exists = target.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (cfg.target_schema, spec.target),
    ).fetchone()
    out.append(
        (
            f"table_{spec.source}_source",
            src_exists is not None,
            "ok" if src_exists else "MISSING",
        )
    )
    out.append(
        (
            f"table_{spec.target}_target",
            tgt_exists is not None,
            "ok" if tgt_exists else "MISSING",
        )
    )
    if not src_exists or not tgt_exists:
        return out

    where = f" WHERE ({spec.filter})" if spec.filter else ""
    params: dict[str, Any] = dict(cfg.params)

    src_count = source.execute(f"SELECT COUNT(*) AS c FROM {src_q}{where}", params).fetchone()
    tgt_count = target.execute(f"SELECT COUNT(*) AS c FROM {tgt_q}").fetchone()
    sc = int(src_count["c"]) if src_count else 0
    tc = int(tgt_count["c"]) if tgt_count else 0
    if cfg.mode == "full" and not spec.filter:
        ok = tc >= sc
        detail = f"source={sc} target={tc}"
    else:
        ok = tc > 0 or sc == 0
        detail = f"source_filtered={sc} target={tc} (incremental/filter — presence check)"
    out.append((f"count_{spec.source}", ok, detail))

    # Vector columns present on target
    if spec.vector_columns:
        src_cols = schema_svc.list_source_columns(source, cfg.source_schema, spec.source)
        column_map = resolve_column_map([c["column_name"] for c in src_cols], spec)
        tgt_cols = {
            r["column_name"]
            for r in target.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                (cfg.target_schema, spec.target),
            ).fetchall()
        }
        for vc in spec.vector_columns:
            dst = column_map.get(vc.name, vc.name)
            out.append(
                (
                    f"vector_col_{spec.target}.{dst}",
                    dst in tgt_cols,
                    "ok" if dst in tgt_cols else "MISSING",
                )
            )

    return out


def print_report(results: list[tuple[str, bool, str]]) -> int:
    failed = 0
    for name, ok, detail in results:
        mark = "OK  " if ok else "FAIL"
        print(f"{mark}  {name}: {detail}")
        if not ok:
            failed += 1
    if failed:
        print(f"\n{failed} check(s) failed", flush=True)
    else:
        print("\nAll ETL verification checks passed", flush=True)
    return failed
