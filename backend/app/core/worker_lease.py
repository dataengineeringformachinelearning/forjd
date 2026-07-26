"""Postgres session advisory leases for in-process supervised workers.

Composition helper — one machine runs a tick; peers no-op. Prefer this over
introducing Airflow/Prefect clusters for background work that already lives
beside the API.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg


@asynccontextmanager
async def try_worker_lease(pool: asyncpg.Pool, lease_name: str) -> AsyncIterator[bool]:
    """Yield ``True`` when this connection holds ``lease_name``.

    Session-level ``pg_try_advisory_lock`` — held for the duration of the
    ``async with`` block, then unlocked. Callers must keep tick work inside
    the block (or accept that peers may start after unlock).
    """
    conn = await pool.acquire()
    leased = False
    try:
        leased = bool(
            await conn.fetchval(
                "SELECT pg_try_advisory_lock(hashtextextended($1, 0))",
                lease_name,
            )
        )
        yield leased
    finally:
        if leased:
            try:
                await conn.fetchval(
                    "SELECT pg_advisory_unlock(hashtextextended($1, 0))",
                    lease_name,
                )
            except Exception:
                # Connection drop releases session locks; avoid masking tick errors.
                pass
        await pool.release(conn)
