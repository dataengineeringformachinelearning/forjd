"""Prefect flow for the secure streaming ingest path.

Coordinates ack + Pathway metadata rollup stats. Soft-fails when Prefect API
is offline (same pattern as pulse/anomaly).
"""

from __future__ import annotations

from typing import Any

from prefect import flow, task


# --- Prefect task: ack metadata (no ciphertext) ---
@task(name="ingest-ack")
def ack_ingest(
    user_id: str,
    tenant_ids: list[str],
    accepted: int,
    event_ids: list[str],
    pathway_ok: bool = False,
    pathway_count: int = 0,
) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "tenant_ids": tenant_ids,
        "accepted": accepted,
        "event_ids": event_ids[:20],
        "pathway_ok": pathway_ok,
        "pathway_count": pathway_count,
        "message": (
            f"prefect ingest ack user={user_id[:8]}… "
            f"tenants={len(tenant_ids)} events={accepted} "
            f"pathway={'ok' if pathway_ok else 'skip'}({pathway_count})"
        ),
    }


# --- Prefect flow ---
@flow(name="forjd-ingest", log_prints=True)
def ingest_flow(
    user_id: str,
    tenant_ids: list[str],
    accepted: int = 0,
    event_ids: list[str] | None = None,
    pathway_ok: bool = False,
    pathway_count: int = 0,
) -> dict[str, Any]:
    result = ack_ingest(
        user_id,
        tenant_ids,
        accepted,
        event_ids or [],
        pathway_ok,
        pathway_count,
    )
    print(result["message"])
    return {"ok": True, **result}


# --- Entry used by the API (local fallback if Prefect is down) ---
def run_ingest_flow(
    *,
    user_id: str,
    tenant_ids: list[str],
    accepted: int,
    event_ids: list[str],
    pathway_ok: bool = False,
    pathway_count: int = 0,
) -> dict[str, Any]:
    try:
        return ingest_flow(
            user_id,
            tenant_ids,
            accepted,
            event_ids,
            pathway_ok,
            pathway_count,
        )
    except Exception as exc:  # noqa: BLE001
        body = ack_ingest.fn(
            user_id,
            tenant_ids,
            accepted,
            event_ids,
            pathway_ok,
            pathway_count,
        )
        return {"ok": True, "mode": "local-fallback", "error": str(exc), **body}
