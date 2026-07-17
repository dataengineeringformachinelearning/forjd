"""Prefect flow — refresh platform threat intel feeds (abuse.ch)."""

from __future__ import annotations

import asyncio
from typing import Any

from prefect import flow, task

from app.pipelines.soft_fail import run_with_local_fallback


# --- Sync task wrapping async service (Prefect flows are sync here) ---
@task(name="threat-intel-fetch-abuse-ch")
def fetch_and_store_abuse_ch(pool: Any) -> dict[str, Any]:
    from app.services import threat_intel as threat_svc

    return asyncio.run(threat_svc.refresh_abuse_ch_platform(pool))


@flow(name="forjd-threat-intel", log_prints=True)
def threat_intel_flow(pool: Any) -> dict[str, Any]:
    result = fetch_and_store_abuse_ch(pool)
    print(f"threat-intel refresh source={result.get('source')} count={result.get('count')}")
    return result


# --- Soft-fail entry (API / cron without Prefect API) ---
def run_threat_intel_refresh(pool: Any) -> dict[str, Any]:
    def _local(exc: Exception) -> dict[str, Any]:
        result = fetch_and_store_abuse_ch.fn(pool)
        return {**result, "mode": "local-fallback", "prefect_error": str(exc)}

    return run_with_local_fallback(threat_intel_flow, pool, fallback=_local)
