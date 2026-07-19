"""Batch extract → transform → upsert with resume watermarks."""

from __future__ import annotations

import logging
import time
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from forjd_etl import schema as schema_svc
from forjd_etl import state as state_svc
from forjd_etl.config import EtlConfig, TableSpec
from forjd_etl.db import qualify, quote_ident, with_retry
from forjd_etl.transforms import (
    apply_transforms,
    apply_vector_validation,
    resolve_column_map,
)

logger = logging.getLogger("forjd.etl.transfer")


# --- Public entry ---
def migrate_table(
    *,
    source: psycopg.Connection,
    target: psycopg.Connection,
    cfg: EtlConfig,
    spec: TableSpec,
    reset: bool = False,
) -> dict[str, Any]:
    if not spec.enabled:
        return {"table": spec.source, "status": "skipped", "rows": 0}

    key = state_svc.table_key(cfg.source_schema, spec.source, cfg.target_schema, spec.target)
    if reset:
        state_svc.reset_checkpoint(
            target, schema=cfg.target_schema, state_table=cfg.state_table, key=key
        )

    src_cols = schema_svc.list_source_columns(source, cfg.source_schema, spec.source)
    if not src_cols:
        raise ValueError(f"source table not found: {cfg.source_schema}.{spec.source}")

    source_names = [c["column_name"] for c in src_cols]
    column_map = resolve_column_map(source_names, spec)

    if cfg.ensure_tables and not cfg.dry_run:
        schema_svc.ensure_table(
            target,
            schema=cfg.target_schema,
            table=spec.target,
            columns=src_cols,
            primary_key=spec.primary_key,
            column_map=column_map,
        )
    if cfg.ensure_columns and not cfg.dry_run:
        schema_svc.ensure_missing_columns(
            target,
            schema=cfg.target_schema,
            table=spec.target,
            source_columns=src_cols,
            column_map=column_map,
        )

    ckpt = state_svc.get_checkpoint(
        target, schema=cfg.target_schema, state_table=cfg.state_table, key=key
    )
    watermark = None
    rows_done = 0
    if ckpt and not reset:
        # Resume: both full and incremental advance a watermark (keyset).
        watermark = state_svc.parse_watermark(ckpt.get("watermark"))
        rows_done = int(ckpt.get("rows_upserted") or 0)
        if cfg.mode == "full" and ckpt.get("status") == "completed" and not reset:
            logger.info("%s already completed (full) — skip (use --reset to redo)", spec.source)
            return {
                "table": spec.source,
                "status": "already_completed",
                "rows": rows_done,
                "watermark": ckpt.get("watermark"),
            }

    select_cols = list(column_map.keys())
    for pk in spec.primary_key:
        if pk not in select_cols:
            raise ValueError(f"{spec.source}: primary_key {pk!r} missing from column map")

    # Target column names that are json/jsonb (need Jsonb adapters on write)
    json_target_cols = {
        column_map[c["column_name"]]
        for c in src_cols
        if c["column_name"] in column_map
        and str(c.get("udt_name") or "").lower() in {"json", "jsonb"}
    }

    if spec.incremental and spec.incremental.column in select_cols:
        order_col = spec.incremental.column
    else:
        order_col = spec.primary_key[0]

    logger.info(
        "migrate %s → %s.%s mode=%s watermark=%s dry_run=%s",
        spec.source,
        cfg.target_schema,
        spec.target,
        cfg.mode,
        state_svc.format_watermark(watermark),
        cfg.dry_run,
    )

    batch_num = 0
    table_errors = 0
    last_wm: Any = watermark

    while True:
        where_parts: list[str] = []
        params: dict[str, Any] = dict(cfg.params)
        if spec.filter:
            where_parts.append(f"({spec.filter})")
        if last_wm is not None:
            where_parts.append(f"{quote_ident(order_col)} > %(etl_watermark)s")
            params["etl_watermark"] = last_wm

        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        col_list = ", ".join(quote_ident(c) for c in select_cols)
        src_q = qualify(cfg.source_schema, spec.source)
        batch_sql = (
            f"SELECT {col_list} FROM {src_q}{where_sql} "
            f"ORDER BY {quote_ident(order_col)} ASC, "
            + ", ".join(quote_ident(p) for p in spec.primary_key)
            + f" ASC LIMIT {cfg.batch_size}"
        )

        batch_num += 1
        t0 = time.monotonic()

        def _fetch(
            _sql: str = batch_sql,
            _params: dict[str, Any] = params,
        ) -> list[dict[str, Any]]:
            cur = source.execute(_sql, _params)
            return [dict(r) for r in cur.fetchall()]

        rows = with_retry(
            _fetch,
            max_retries=cfg.max_retries,
            backoff_seconds=cfg.retry_backoff_seconds,
            label=f"fetch {spec.source} batch {batch_num}",
        )
        if not rows:
            break

        upserted = 0
        batch_errors = 0
        pk_targets = [column_map[p] for p in spec.primary_key]
        mapped_rows: list[dict[str, Any]] = []
        for row in rows:
            try:
                mapped = apply_transforms(row, spec.transforms, column_map=column_map)
                mapped = apply_vector_validation(
                    mapped, spec.vector_columns, column_map=column_map
                )
                mapped_rows.append(mapped)
                last_wm = row.get(order_col, last_wm)
            except Exception as exc:  # noqa: BLE001
                batch_errors += 1
                table_errors += 1
                logger.exception(
                    "transform error on %s pk=%s: %s",
                    spec.source,
                    {p: row.get(p) for p in spec.primary_key},
                    exc,
                )
                if cfg.max_table_errors and table_errors >= cfg.max_table_errors:
                    raise RuntimeError(
                        f"{spec.source}: max_table_errors={cfg.max_table_errors} reached"
                    ) from exc

        if mapped_rows and not cfg.dry_run:
            try:

                def _write_batch(
                    _rows: list[dict[str, Any]] = mapped_rows,
                    _pk: list[str] = pk_targets,
                    _json_cols: set[str] = json_target_cols,
                ) -> int:
                    return _upsert_batch(
                        target,
                        schema=cfg.target_schema,
                        table=spec.target,
                        rows=_rows,
                        primary_key=_pk,
                        json_columns=_json_cols,
                    )

                upserted = with_retry(
                    _write_batch,
                    max_retries=cfg.max_retries,
                    backoff_seconds=cfg.retry_backoff_seconds,
                    label=f"upsert-batch {spec.source}",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "batch upsert failed on %s (%s); falling back to row writes",
                    spec.source,
                    type(exc).__name__,
                )
                for mapped in mapped_rows:
                    try:

                        def _write(
                            _row: dict[str, Any] = mapped,
                            _pk: list[str] = pk_targets,
                            _json_cols: set[str] = json_target_cols,
                        ) -> None:
                            _upsert_row(
                                target,
                                schema=cfg.target_schema,
                                table=spec.target,
                                row=_row,
                                primary_key=_pk,
                                json_columns=_json_cols,
                            )

                        with_retry(
                            _write,
                            max_retries=cfg.max_retries,
                            backoff_seconds=cfg.retry_backoff_seconds,
                            label=f"upsert {spec.source}",
                        )
                        upserted += 1
                    except Exception as row_exc:  # noqa: BLE001
                        batch_errors += 1
                        table_errors += 1
                        logger.exception(
                            "row error on %s: %s",
                            spec.source,
                            row_exc,
                        )
                        if cfg.max_table_errors and table_errors >= cfg.max_table_errors:
                            raise RuntimeError(
                                f"{spec.source}: max_table_errors="
                                f"{cfg.max_table_errors} reached"
                            ) from row_exc
        elif mapped_rows and cfg.dry_run:
            upserted = len(mapped_rows)

        rows_done += upserted
        elapsed = time.monotonic() - t0
        logger.info(
            "progress %s batch=%s fetched=%s upserted=%s errors=%s total=%s %.2fs",
            spec.source,
            batch_num,
            len(rows),
            upserted,
            batch_errors,
            rows_done,
            elapsed,
        )

        if not cfg.dry_run:
            ckpt_wm = last_wm
            ckpt_rows = rows_done
            ckpt_batch = batch_num
            ckpt_errors = table_errors

            def _ckpt(
                _wm: Any = ckpt_wm,
                _rows: int = ckpt_rows,
                _batch: int = ckpt_batch,
                _errors: int = ckpt_errors,
            ) -> None:
                state_svc.upsert_checkpoint(
                    target,
                    schema=cfg.target_schema,
                    state_table=cfg.state_table,
                    key=key,
                    source_table=spec.source,
                    target_table=spec.target,
                    mode=cfg.mode,
                    watermark=state_svc.format_watermark(_wm),
                    rows_upserted=_rows,
                    status="running",
                    meta={"batch": _batch, "errors": _errors},
                )
                target.commit()

            with_retry(
                _ckpt,
                max_retries=cfg.max_retries,
                backoff_seconds=cfg.retry_backoff_seconds,
                label=f"checkpoint {spec.source}",
            )

        if len(rows) < cfg.batch_size:
            break

    if not cfg.dry_run:
        state_svc.upsert_checkpoint(
            target,
            schema=cfg.target_schema,
            state_table=cfg.state_table,
            key=key,
            source_table=spec.source,
            target_table=spec.target,
            mode=cfg.mode,
            watermark=state_svc.format_watermark(last_wm),
            rows_upserted=rows_done,
            status="completed",
            meta={"batches": batch_num, "errors": table_errors},
        )
        target.commit()

    return {
        "table": spec.source,
        "target": f"{cfg.target_schema}.{spec.target}",
        "status": "completed",
        "rows": rows_done,
        "errors": table_errors,
        "watermark": state_svc.format_watermark(last_wm),
        "dry_run": cfg.dry_run,
    }


def _adapt_value(value: Any, *, is_json: bool) -> Any:
    """Adapt Python values for psycopg (json/jsonb needs Jsonb wrapper)."""
    if value is None:
        return None
    if is_json and isinstance(value, (dict, list)):
        return Jsonb(value)
    # Defensive: dict always means JSON from source decode
    if isinstance(value, dict):
        return Jsonb(value)
    return value


def _upsert_statement(
    *,
    schema: str,
    table: str,
    cols: list[str],
    primary_key: list[str],
) -> sql.Composed:
    qtable = sql.Identifier(schema, table)
    col_ids = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
    placeholders = sql.SQL(", ").join(sql.Placeholder() * len(cols))
    pk_ids = sql.SQL(", ").join(sql.Identifier(c) for c in primary_key)
    non_pk = [c for c in cols if c not in primary_key]
    if non_pk:
        set_clause = sql.SQL(", ").join(
            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c)) for c in non_pk
        )
        conflict = sql.SQL("ON CONFLICT ({}) DO UPDATE SET {}").format(pk_ids, set_clause)
    else:
        conflict = sql.SQL("ON CONFLICT ({}) DO NOTHING").format(pk_ids)
    return sql.SQL("INSERT INTO {} ({}) VALUES ({}) {}").format(
        qtable, col_ids, placeholders, conflict
    )


def _upsert_batch(
    conn: psycopg.Connection,
    *,
    schema: str,
    table: str,
    rows: list[dict[str, Any]],
    primary_key: list[str],
    json_columns: set[str] | None = None,
) -> int:
    if not rows:
        return 0
    json_columns = json_columns or set()
    cols = list(rows[0].keys())
    stmt = _upsert_statement(
        schema=schema, table=table, cols=cols, primary_key=primary_key
    )
    params = [
        [_adapt_value(row[c], is_json=c in json_columns) for c in cols] for row in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(stmt, params)
    return len(rows)


def _upsert_row(
    conn: psycopg.Connection,
    *,
    schema: str,
    table: str,
    row: dict[str, Any],
    primary_key: list[str],
    json_columns: set[str] | None = None,
) -> None:
    cols = list(row.keys())
    if not cols:
        return
    json_columns = json_columns or set()
    stmt = _upsert_statement(
        schema=schema, table=table, cols=cols, primary_key=primary_key
    )
    params = [_adapt_value(row[c], is_json=c in json_columns) for c in cols]
    conn.execute(stmt, params)
