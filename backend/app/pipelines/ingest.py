"""Prefect flow for the secure streaming ingest path.

Ack-only for now — Pathway continuous jobs and Redpanda replacement land next.
Soft-fails when Prefect API is offline (same pattern as pulse/anomaly).
"""

from __future__ import annotations

from typing import Any

from prefect import flow, task


@task(name="ingest-ack")
def ack_ingest(
    user_id: str,
    tenant_ids: list[str],
    accepted: int,
    event_ids: list[str],
) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "tenant_ids": tenant_ids,
        "accepted": accepted,
        "event_ids": event_ids[:20],
        "message": (
            f"prefect ingest ack user={user_id[:8]}… "
            f"tenants={len(tenant_ids)} events={accepted}"
        ),
    }


@flow(name="forjd-ingest", log_prints=True)
def ingest_flow(
    user_id: str,
    tenant_ids: list[str],
    accepted: int = 0,
    event_ids: list[str] | None = None,
) -> dict[str, Any]:
    result = ack_ingest(user_id, tenant_ids, accepted, event_ids or [])
    print(result["message"])
    return {"ok": True, **result}


def run_ingest_flow(
    *,
    user_id: str,
    tenant_ids: list[str],
    accepted: int,
    event_ids: list[str],
) -> dict[str, Any]:
    try:
        return ingest_flow(user_id, tenant_ids, accepted, event_ids)
    except Exception as exc:  # noqa: BLE001
        body = ack_ingest.fn(user_id, tenant_ids, accepted, event_ids)
        return {"ok": True, "mode": "local-fallback", "error": str(exc), **body}
