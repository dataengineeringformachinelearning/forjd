"""Prefect flow for the unsupervised anomaly PoC."""

from __future__ import annotations

from typing import Any

from prefect import flow, task


@task(name="anomaly-ack")
def ack_anomaly(
    series_id: str,
    action: str,
    n_windows: int,
    final_loss: float,
    is_anomaly: bool | None = None,
) -> dict[str, Any]:
    flag = "" if is_anomaly is None else f" anomaly={is_anomaly}"
    return {
        "series_id": series_id,
        "action": action,
        "n_windows": n_windows,
        "final_loss": final_loss,
        "is_anomaly": is_anomaly,
        "message": (
            f"prefect anomaly {action} {series_id} "
            f"windows={n_windows} loss={final_loss:.6f}{flag}"
        ),
    }


@flow(name="forjd-anomaly", log_prints=True)
def anomaly_flow(
    series_id: str,
    action: str,
    n_windows: int = 0,
    final_loss: float = 0.0,
    is_anomaly: bool | None = None,
) -> dict[str, Any]:
    result = ack_anomaly(series_id, action, n_windows, final_loss, is_anomaly)
    print(result["message"])
    return {"ok": True, **result}


def run_anomaly_flow(
    *,
    series_id: str,
    action: str,
    n_windows: int,
    final_loss: float,
    is_anomaly: bool | None = None,
) -> dict[str, Any]:
    try:
        return anomaly_flow(
            series_id, action, n_windows, final_loss, is_anomaly
        )
    except Exception as exc:
        body = ack_anomaly.fn(
            series_id, action, n_windows, final_loss, is_anomaly
        )
        return {"ok": True, "mode": "local-fallback", "error": str(exc), **body}
