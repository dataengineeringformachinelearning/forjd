"""Pulse PoC API — Angular → FastAPI → stack layers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.services import engine
from app.services.pulse import last_pulse, recent_pulses, run_pulse

router = APIRouter(prefix="/pulse", tags=["pulse"])


class PulseRequest(BaseModel):
    values: list[float] = Field(
        default_factory=lambda: [1.0, 2.0, 3.0, 5.0, 8.0],
        min_length=1,
        max_length=64,
    )
    source: str = Field(default="api", max_length=64)


@router.post("")
async def create_pulse(request: Request, body: PulseRequest) -> dict[str, Any]:
    """Run one connected pulse across engine / Polars / Pathway / Prefect / DB / cache."""
    return await run_pulse(
        pool=getattr(request.app.state, "db_pool", None),
        redis=getattr(request.app.state, "redis", None),
        values=body.values,
        source=body.source,
    )


@router.get("")
async def get_pulse(request: Request) -> dict[str, Any]:
    """Last cached pulse + recent Postgres rows + engine status."""
    redis = getattr(request.app.state, "redis", None)
    pool = getattr(request.app.state, "db_pool", None)
    return {
        "engine": engine.engine_status(),
        "cached": await last_pulse(redis),
        "recent": await recent_pulses(pool, limit=5),
    }
