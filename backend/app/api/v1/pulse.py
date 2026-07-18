"""Pulse PoC API — Angular → FastAPI → stack layers.

POST requires a bearer principal in production; local/dev smoke checks stay open.
GET remains available for ops status.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.core.auth import AuthUser, get_current_user
from app.core.config import settings
from app.services import engine
from app.services.pulse import last_pulse, recent_pulses, run_pulse

router = APIRouter(prefix="/pulse", tags=["pulse"])
_bearer = HTTPBearer(auto_error=False)


class PulseRequest(BaseModel):
    values: list[float] = Field(
        default_factory=lambda: [1.0, 2.0, 3.0, 5.0, 8.0],
        min_length=1,
        max_length=64,
    )
    source: str = Field(default="api", max_length=64)


# --- Production write gate ---
async def require_auth_in_production(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser | None:
    """Fail closed on unauthenticated pulse writes in production / Fly."""
    if not settings.is_production:
        return None
    return await get_current_user(request, creds)


@router.post("")
async def create_pulse(
    request: Request,
    body: PulseRequest,
    _user: AuthUser | None = Depends(require_auth_in_production),
) -> dict[str, Any]:
    """Run one connected pulse across engine / Polars / Pathway / Prefect / DB / cache."""
    del _user
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
