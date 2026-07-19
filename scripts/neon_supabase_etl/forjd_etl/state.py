"""Idempotent ETL checkpoints (watermarks) in the target database."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import psycopg

from forjd_etl.db import qualify

logger = logging.getLogger("forjd.etl.state")


# --- DDL ---
def ensure_state_table(conn: psycopg.Connection, schema: str, table: str) -> None:
    q = qualify(schema, table)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {q} (
            table_key TEXT PRIMARY KEY,
            source_table TEXT NOT NULL,
            target_table TEXT NOT NULL,
            mode TEXT NOT NULL,
            watermark TEXT,
            rows_upserted BIGINT NOT NULL DEFAULT 0,
            last_batch_at TIMESTAMPTZ,
            last_error TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            meta JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def table_key(source_schema: str, source: str, target_schema: str, target: str) -> str:
    return f"{source_schema}.{source}->{target_schema}.{target}"


# --- Read / write ---
def get_checkpoint(
    conn: psycopg.Connection,
    *,
    schema: str,
    state_table: str,
    key: str,
) -> dict[str, Any] | None:
    q = qualify(schema, state_table)
    row = conn.execute(
        f"SELECT * FROM {q} WHERE table_key = %s",
        (key,),
    ).fetchone()
    return dict(row) if row else None


def upsert_checkpoint(
    conn: psycopg.Connection,
    *,
    schema: str,
    state_table: str,
    key: str,
    source_table: str,
    target_table: str,
    mode: str,
    watermark: str | None,
    rows_upserted: int,
    status: str,
    last_error: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    q = qualify(schema, state_table)
    conn.execute(
        f"""
        INSERT INTO {q} (
            table_key, source_table, target_table, mode, watermark,
            rows_upserted, last_batch_at, last_error, status, meta, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s::jsonb, NOW()
        )
        ON CONFLICT (table_key) DO UPDATE SET
            watermark = EXCLUDED.watermark,
            rows_upserted = EXCLUDED.rows_upserted,
            last_batch_at = EXCLUDED.last_batch_at,
            last_error = EXCLUDED.last_error,
            status = EXCLUDED.status,
            meta = EXCLUDED.meta,
            mode = EXCLUDED.mode,
            updated_at = NOW()
        """,
        (
            key,
            source_table,
            target_table,
            mode,
            watermark,
            rows_upserted,
            last_error,
            status,
            json.dumps(meta or {}),
        ),
    )


def parse_watermark(raw: str | None) -> datetime | str | None:
    if raw is None or raw == "":
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw


def format_watermark(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def reset_checkpoint(
    conn: psycopg.Connection,
    *,
    schema: str,
    state_table: str,
    key: str,
) -> None:
    q = qualify(schema, state_table)
    conn.execute(f"DELETE FROM {q} WHERE table_key = %s", (key,))
    logger.info("reset checkpoint %s", key)
