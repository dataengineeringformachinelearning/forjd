"""Postgres connections and retry helpers (psycopg3)."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger("forjd.etl.db")


# --- DSN helpers ---
def normalize_dsn(raw: str) -> str:
    dsn = raw.strip()
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if dsn.startswith(prefix):
            dsn = "postgresql://" + dsn.removeprefix(prefix)
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn.removeprefix("postgres://")
    return dsn


def resolve_source_dsn() -> str:
    raw = (
        os.environ.get("NEON_DATABASE_URL") or os.environ.get("SOURCE_DATABASE_URL") or ""
    ).strip()
    if not raw:
        raise RuntimeError("Set NEON_DATABASE_URL or SOURCE_DATABASE_URL")
    return normalize_dsn(raw)


def resolve_target_dsn() -> str:
    raw = (
        os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("TARGET_DATABASE_URL") or ""
    ).strip()
    if not raw:
        raise RuntimeError("Set SUPABASE_DATABASE_URL or TARGET_DATABASE_URL")
    dsn = normalize_dsn(raw)
    parsed = urlparse(dsn)
    host = (parsed.hostname or "").lower()
    port = parsed.port or 5432
    if "pooler.supabase.com" in host or port == 6543:
        raise RuntimeError(
            "Use Supabase DIRECT URI (db.<ref>.supabase.co:5432), not transaction pooler :6543"
        )
    return dsn


@contextmanager
def connect(dsn: str) -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- Retry ---
def with_retry[T](
    fn: Callable[[], T],
    *,
    max_retries: int,
    backoff_seconds: float,
    label: str,
) -> T:
    attempt = 0
    while True:
        try:
            return fn()
        except (psycopg.OperationalError, psycopg.InterfaceError, TimeoutError) as exc:
            attempt += 1
            if attempt > max_retries:
                logger.error("%s failed after %s retries: %s", label, max_retries, exc)
                raise
            sleep_for = backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "%s transient error (attempt %s/%s): %s — sleep %.1fs",
                label,
                attempt,
                max_retries,
                type(exc).__name__,
                sleep_for,
            )
            time.sleep(sleep_for)


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def qualify(schema: str, table: str) -> str:
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def redacted_dsn_label(dsn: str) -> str:
    """Safe label for logs (host only)."""
    try:
        p = urlparse(normalize_dsn(dsn))
        return f"{p.hostname}:{p.port or 5432}/{p.path.lstrip('/')}"
    except Exception:
        return "(dsn)"
