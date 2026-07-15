"""Shared Postgres (asyncpg) + Redis (Dragonfly) client helpers.

DSN note: Settings use SQLAlchemy-style `postgresql+asyncpg://…`.
asyncpg wants a plain `postgresql://…` URL — we normalize once here.
"""

from __future__ import annotations

import logging

import asyncpg
from redis import asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger("forjd.clients")


def asyncpg_dsn(dsn: str | None = None) -> str:
    raw = dsn or settings.POSTGRES_DSN
    return raw.replace("postgresql+asyncpg://", "postgresql://", 1)


async def create_db_pool() -> asyncpg.Pool | None:
    try:
        pool = await asyncpg.create_pool(dsn=asyncpg_dsn(), min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        logger.info("postgres connected")
        return pool
    except Exception:
        logger.exception("postgres unavailable — app will start; /ready will fail")
        return None


async def create_redis_client() -> aioredis.Redis | None:
    try:
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
        logger.info("redis connected")
        return client
    except Exception:
        logger.exception("redis unavailable — app will start; /ready will fail")
        return None
