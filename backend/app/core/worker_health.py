"""In-process health accounting for supervised durable workers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

MAX_CONSECUTIVE_FAILURES = 3


@dataclass
class _WorkerState:
    started_at: datetime
    stale_after_seconds: float
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error_type: str | None = None
    consecutive_failures: int = 0


class WorkerHealthRegistry:
    """Track successful ticks separately from merely live asyncio tasks."""

    def __init__(self) -> None:
        self._states: dict[str, _WorkerState] = {}

    def started(self, name: str, *, stale_after_seconds: float) -> None:
        self._states[name] = _WorkerState(
            started_at=datetime.now(UTC),
            stale_after_seconds=max(1.0, float(stale_after_seconds)),
        )

    def succeeded(self, name: str) -> None:
        state = self._states.get(name)
        if state is None:
            self.started(name, stale_after_seconds=60.0)
            state = self._states[name]
        state.last_success_at = datetime.now(UTC)
        state.consecutive_failures = 0

    def failed(self, name: str, exc: Exception) -> None:
        state = self._states.get(name)
        if state is None:
            self.started(name, stale_after_seconds=60.0)
            state = self._states[name]
        state.last_error_at = datetime.now(UTC)
        state.last_error_type = type(exc).__name__
        state.consecutive_failures += 1

    def status(self, name: str, *, now: datetime | None = None) -> tuple[bool, dict[str, Any]]:
        state = self._states.get(name)
        if state is None:
            return False, {
                "state": "unreported",
                "last_success_at": None,
                "last_error_at": None,
                "last_error_type": None,
                "consecutive_failures": 0,
            }
        observed_at = now or datetime.now(UTC)
        reference = state.last_success_at or state.started_at
        stale_for = max(0.0, (observed_at - reference).total_seconds())
        if state.last_success_at is None:
            health_state = "starting"
            healthy = False
        elif state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            health_state = "failed"
            healthy = False
        elif stale_for > state.stale_after_seconds:
            health_state = "stale"
            healthy = False
        elif state.consecutive_failures:
            health_state = "degraded"
            healthy = True
        else:
            health_state = "healthy"
            healthy = True
        return healthy, {
            "state": health_state,
            "last_success_at": (
                state.last_success_at.isoformat() if state.last_success_at is not None else None
            ),
            "last_error_at": (
                state.last_error_at.isoformat() if state.last_error_at is not None else None
            ),
            "last_error_type": state.last_error_type,
            "consecutive_failures": state.consecutive_failures,
            "stale_after_seconds": state.stale_after_seconds,
        }
