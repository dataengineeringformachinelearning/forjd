"""Prefect flow — hourly analytics rollup for a tenant."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from prefect import flow, task

from app.pipelines.soft_fail import run_with_local_fallback


@task(name="analytics-aggregate-hour")
def aggregate_hour_task(pool: Any, tenant_id: str) -> dict[str, Any]:
    from app.services import analytics as analytics_svc

    return asyncio.run(analytics_svc.aggregate_hour(pool, tenant_id=UUID(tenant_id)))


@flow(name="forjd-analytics-aggregate", log_prints=True)
def analytics_aggregate_flow(pool: Any, tenant_id: str) -> dict[str, Any]:
    result = aggregate_hour_task(pool, tenant_id)
    print(f"analytics aggregate tenant={tenant_id[:8]}… ok={result.get('ok')}")
    return result


def run_analytics_aggregate(pool: Any, tenant_id: str) -> dict[str, Any]:
    def _local(exc: Exception) -> dict[str, Any]:
        result = aggregate_hour_task.fn(pool, tenant_id)
        return {**result, "mode": "local-fallback", "prefect_error": str(exc)}

    return run_with_local_fallback(analytics_aggregate_flow, pool, tenant_id, fallback=_local)
