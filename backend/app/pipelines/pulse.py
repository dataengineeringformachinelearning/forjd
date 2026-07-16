"""Prefect flow for the pulse PoC.

Runs against PREFECT_API_URL when the server is up. Soft-fails so the API
still returns a useful payload when Prefect is offline.
"""

from __future__ import annotations

from typing import Any

from prefect import flow, task


@task(name="pulse-ack")
def ack_pulse(pulse_id: str, n_values: int) -> dict[str, Any]:
    return {
        "pulse_id": pulse_id,
        "n_values": n_values,
        "message": f"prefect ack {pulse_id[:8]}… ({n_values} values)",
    }


@flow(name="forjd-pulse", log_prints=True)
def pulse_flow(pulse_id: str, n_values: int = 0) -> dict[str, Any]:
    result = ack_pulse(pulse_id, n_values)
    print(result["message"])
    return {"ok": True, **result}


def run_pulse_flow(*, pulse_id: str, n_values: int) -> dict[str, Any]:
    """Invoke the flow; on API/client errors fall back to the task body."""
    try:
        return pulse_flow(pulse_id, n_values)
    except Exception as exc:
        # Local/dev without Prefect server — still exercise the task logic.
        body = ack_pulse.fn(pulse_id, n_values)
        return {"ok": True, "mode": "local-fallback", "error": str(exc), **body}
