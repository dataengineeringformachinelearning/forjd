"""Target schema / extension / table shape management."""

from __future__ import annotations

import logging
from typing import Any

import psycopg

from forjd_etl.db import qualify, quote_ident

logger = logging.getLogger("forjd.etl.schema")


# --- Extensions + schema ---
def ensure_extensions(conn: psycopg.Connection, extensions: list[str]) -> None:
    for ext in extensions:
        name = ext.strip()
        if not name:
            continue
        logger.info("ensure extension %s", name)
        conn.execute(f'CREATE EXTENSION IF NOT EXISTS "{name}"')


def ensure_schema(conn: psycopg.Connection, schema: str) -> None:
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(schema)}")


# --- Source column introspection ---
def list_source_columns(
    conn: psycopg.Connection,
    schema: str,
    table: str,
) -> list[dict[str, Any]]:
    """Return column metadata including format_type (handles vector(n))."""
    rows = conn.execute(
        """
        SELECT
            a.attname AS column_name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) AS format_type,
            NOT a.attnotnull AS is_nullable,
            pg_get_expr(ad.adbin, ad.adrelid) AS column_default,
            t.typname AS udt_name
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
        WHERE n.nspname = %s
          AND c.relname = %s
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        (schema, table),
    ).fetchall()
    return [dict(r) for r in rows]


def ensure_table(
    conn: psycopg.Connection,
    *,
    schema: str,
    table: str,
    columns: list[dict[str, Any]],
    primary_key: list[str],
    column_map: dict[str, str],
) -> None:
    """CREATE TABLE IF NOT EXISTS with mapped column names and PK."""
    q = qualify(schema, table)
    exists = conn.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table),
    ).fetchone()
    if exists:
        return

    col_sql: list[str] = []
    src_by_name = {c["column_name"]: c for c in columns}
    for src, dst in column_map.items():
        meta = src_by_name.get(src)
        if meta is None:
            continue
        typ = str(meta["format_type"])
        null_sql = "" if meta.get("is_nullable") else " NOT NULL"
        col_sql.append(f"{quote_ident(dst)} {typ}{null_sql}")

    if not col_sql:
        raise ValueError(f"no columns to create for {schema}.{table}")

    pk_targets = [column_map[p] for p in primary_key if p in column_map]
    pk_sql = ""
    if pk_targets:
        pk_sql = ", PRIMARY KEY (" + ", ".join(quote_ident(p) for p in pk_targets) + ")"

    ddl = f"CREATE TABLE {q} (\n  " + ",\n  ".join(col_sql) + pk_sql + "\n)"
    logger.info("create table %s (%s cols)", q, len(col_sql))
    conn.execute(ddl)


def ensure_missing_columns(
    conn: psycopg.Connection,
    *,
    schema: str,
    table: str,
    source_columns: list[dict[str, Any]],
    column_map: dict[str, str],
) -> None:
    existing = {
        r["column_name"]
        for r in conn.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (schema, table),
        ).fetchall()
    }
    src_by_name = {c["column_name"]: c for c in source_columns}
    q = qualify(schema, table)
    for src, dst in column_map.items():
        if dst in existing:
            continue
        meta = src_by_name.get(src)
        if meta is None:
            continue
        typ = str(meta["format_type"])
        logger.info("add column %s.%s %s", q, dst, typ)
        conn.execute(f"ALTER TABLE {q} ADD COLUMN {quote_ident(dst)} {typ}")
