"""Shared Postgres (asyncpg) + Redis (Dragonfly) client helpers.

DSN note: Settings use SQLAlchemy-style `postgresql+asyncpg://…`.
asyncpg wants a plain `postgresql://…` URL — we normalize once here.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from urllib.parse import urlparse, urlunparse

import asyncpg
from redis import asyncio as aioredis
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.core.config import settings

logger = logging.getLogger("forjd.clients")


def asyncpg_dsn(dsn: str | None = None) -> str:
    raw = dsn or settings.POSTGRES_DSN
    return raw.replace("postgresql+asyncpg://", "postgresql://", 1)


def prefer_fly_ipv6_url(url: str) -> str:
    """Rewrite Fly `*.internal` / `*.flycast` hosts to literal IPv6 for redis-py.

    Fly private DNS is AAAA-only. Some clients still fail open_connection on the
    hostname; connecting to `[fdaa:…]` is reliable on Machines.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return url
    if not (host.endswith(".internal") or host.endswith(".flycast")):
        return url
    port = parsed.port or 6379
    try:
        infos = socket.getaddrinfo(host, port, family=socket.AF_INET6, type=socket.SOCK_STREAM)
    except OSError as exc:
        logger.warning("IPv6 resolve failed for %s: %s", host, exc)
        return url
    if not infos:
        return url
    ipv6 = infos[0][4][0]
    userinfo = ""
    if parsed.username is not None or parsed.password is not None:
        user = parsed.username or ""
        # redis://:password@host → empty user, password set
        userinfo = f"{user}:{parsed.password}@" if parsed.password is not None else f"{user}@"
    netloc = f"{userinfo}[{ipv6}]:{port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


async def create_db_pool() -> asyncpg.Pool | None:
    try:
        pool = await asyncpg.create_pool(
            dsn=asyncpg_dsn(),
            min_size=max(1, settings.DB_POOL_MIN),
            max_size=max(settings.DB_POOL_MIN, settings.DB_POOL_MAX),
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
        redis_url = prefer_fly_ipv6_url(settings.REDIS_URL)
        client = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=False,
            retry=Retry(NoBackoff(), retries=0),
            health_check_interval=0,
        )
        # Cap soft-connect so missing Dragonfly does not stall API boot.
        await asyncio.wait_for(client.ping(), timeout=3)
        logger.info("redis connected")
        return client
    except Exception:
        logger.exception("redis unavailable — app will start; /ready will fail")
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()
        return None
