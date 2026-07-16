"""End-to-end pulse PoC — touches Postgres, Dragonfly, Rust engine, Polars, Pathway, Prefect."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import asyncpg
from redis.asyncio import Redis

from app.pipelines.pulse import run_pulse_flow
from app.services import batch, engine

logger = logging.getLogger("forjd.pulse")

CACHE_KEY = "forjd:pulse:last"
CACHE_TTL_SECONDS = 60 * 60


async def ensure_pulse_table(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS pulses (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            source TEXT NOT NULL DEFAULT 'api',
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            result JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )


async def run_pulse(
    *,
    pool: asyncpg.Pool | None,
    redis: Redis | None,
    values: list[float] | None = None,
    source: str = "api",
) -> dict[str, Any]:
    values = values or [1.0, 2.0, 3.0, 5.0, 8.0]
    pulse_id = str(uuid.uuid4())
    ts = int(time.time())

    layers: dict[str, Any] = {}

    # Rust engine (PyO3)
    try:
        processed = engine.process_event(
            {
                "id": pulse_id,
                "timestamp": ts,
                "payload": {"values": values, "source": source},
            }
        )
        summarized = engine.summarize_values(values)
        layers["engine"] = {
            "ok": True,
            "event": processed,
            "summary": summarized,
            "status": engine.engine_status(),
        }
    except Exception as exc:
        logger.exception("engine layer failed")
        layers["engine"] = {"ok": False, "error": str(exc), "status": engine.engine_status()}

    # Polars batch
    try:
        layers["polars"] = {"ok": True, **batch.polars_summary(values)}
    except Exception as exc:
        logger.exception("polars layer failed")
        layers["polars"] = {"ok": False, "error": str(exc)}

    # Pathway stream demo (finite)
    layers["pathway"] = batch.pathway_increment(values)

    # Prefect orchestration
    try:
        layers["prefect"] = run_pulse_flow(pulse_id=pulse_id, n_values=len(values))
    except Exception as exc:
        logger.exception("prefect layer failed")
        layers["prefect"] = {"ok": False, "error": str(exc)}

    # Postgres (Supabase or local)
    layers["postgres"] = {"ok": False}
    if pool is not None:
        try:
            await ensure_pulse_table(pool)
            await pool.execute(
                """
                INSERT INTO pulses (id, source, payload, result)
                VALUES ($1::uuid, $2, $3::jsonb, $4::jsonb)
                """,
                pulse_id,
                source,
                json.dumps({"values": values}),
                json.dumps(layers),
            )
            layers["postgres"] = {"ok": True, "id": pulse_id}
        except Exception as exc:
            logger.exception("postgres layer failed")
            layers["postgres"] = {"ok": False, "error": str(exc)}
    else:
        layers["postgres"] = {"ok": False, "error": "pool not connected"}

    # Dragonfly / Redis cache
    layers["dragonfly"] = {"ok": False}
    if redis is not None:
        try:
            cached = {
                "id": pulse_id,
                "timestamp": ts,
                "values": values,
                "layers_ok": {k: bool(v.get("ok")) for k, v in layers.items()},
            }
            await redis.set(CACHE_KEY, json.dumps(cached), ex=CACHE_TTL_SECONDS)
            layers["dragonfly"] = {"ok": True, "key": CACHE_KEY, "ttl": CACHE_TTL_SECONDS}
        except Exception as exc:
            logger.exception("dragonfly layer failed")
            layers["dragonfly"] = {"ok": False, "error": str(exc)}
    else:
        layers["dragonfly"] = {"ok": False, "error": "redis not connected"}

    ok_count = sum(1 for v in layers.values() if v.get("ok"))
    return {
        "id": pulse_id,
        "timestamp": ts,
        "values": values,
        "ok": ok_count == len(layers),
        "layers_ok": ok_count,
        "layers_total": len(layers),
        "layers": layers,
    }


async def last_pulse(redis: Redis | None) -> dict[str, Any] | None:
    if redis is None:
        return None
    raw = await redis.get(CACHE_KEY)
    if not raw:
        return None
    return json.loads(raw)


async def recent_pulses(pool: asyncpg.Pool | None, limit: int = 5) -> list[dict[str, Any]]:
    if pool is None:
        return []
    try:
        rows = await pool.fetch(
            """
            SELECT id::text, created_at, source, payload, result
            FROM pulses
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    except Exception:
        logger.exception("failed to list pulses")
        return []

    out: list[dict[str, Any]] = []
    for row in rows:
        payload = row["payload"]
        result = row["result"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if isinstance(result, str):
            result = json.loads(result)
        out.append(
            {
                "id": row["id"],
                "created_at": row["created_at"].isoformat(),
                "source": row["source"],
                "payload": payload,
                "result": result,
            }
        )
    return out
