"""Shared Postgres (asyncpg) + Redis (Dragonfly) client helpers.

DSN note: Settings use SQLAlchemy-style `postgresql+asyncpg://…`.
asyncpg wants a plain `postgresql://…` URL — we normalize once here.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import asyncpg
from redis import asyncio as aioredis
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.core.config import settings

logger = logging.getLogger("forjd.clients")


def asyncpg_dsn(dsn: str | None = None) -> str:
    raw = dsn or settings.POSTGRES_DSN
    return raw.replace("postgresql+asyncpg://", "postgresql://", 1)


async def create_db_pool() -> asyncpg.Pool | None:
    try:
        pool = await asyncpg.create_pool(
            dsn=asyncpg_dsn(),
            min_size=1,
            max_size=5,
            timeout=5,
            command_timeout=5,
        )
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        logger.info("postgres connected")
        return pool
    except Exception:
        logger.exception("postgres unavailable — app will start; /ready will fail")
        return None


async def create_redis_client() -> aioredis.Redis | None:
    client: aioredis.Redis | None = None
    try:
        client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            retry_on_timeout=False,
            retry=Retry(NoBackoff(), retries=0),
            health_check_interval=0,
        )
        # Cap soft-connect so missing Dragonfly does not stall API boot.
        await asyncio.wait_for(client.ping(), timeout=2)
        logger.info("redis connected")
        return client
    except Exception:
        logger.exception("redis unavailable — app will start; /ready will fail")
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()
        return None
