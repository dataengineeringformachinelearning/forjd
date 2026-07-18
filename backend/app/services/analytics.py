"""Tenant analytics rollups + CES overview formulas ."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.services import tenants as tenant_svc


async def ensure_analytics_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS aggregated_analytics (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            bucket_start TIMESTAMPTZ NOT NULL,
            bucket_size TEXT NOT NULL DEFAULT '1h',
            total_requests BIGINT NOT NULL DEFAULT 0,
            avg_latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
            p99_latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
            error_rate_percent DOUBLE PRECISION NOT NULL DEFAULT 0,
            threats_detected INT NOT NULL DEFAULT 0,
            active_incidents INT NOT NULL DEFAULT 0,
            unique_visitors INT NOT NULL DEFAULT 0,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, bucket_start, bucket_size)
        )
        """
    )


# --- Pure formulas ---
def percentile_index(total: int, pct: float = 0.99) -> int:
    if total <= 0:
        return 0
    return max(0, math.ceil(total * pct) - 1)


def ces_composite(
    *,
    uptime_pct: float,
    incidents: int,
    p99_ms: float,
) -> dict[str, float]:
    ces_threat = min(100.0, incidents * 20 + (30.0 if p99_ms > 500 else 0.0))
    ces_sla = max(0.0, uptime_pct - (5.0 if p99_ms > 800 else 0.0))
    ces_stability = max(0.0, 100.0 - incidents * 10 - (15.0 if p99_ms > 300 else 0.0))
    level = max(
        0.0,
        min(100.0, ces_sla * 0.5 + ces_stability * 0.4 + (100.0 - ces_threat) * 0.1),
    )
    return {
        "ces_threat": ces_threat,
        "ces_sla": ces_sla,
        "ces_stability": ces_stability,
        "ces_level": level,
    }


def uptime_status(ratio: float) -> str:
    if ratio >= 1.0:
        return "operational"
    if ratio >= 0.95:
        return "partial_outage"
    return "major_outage"


# --- Hourly rollup from stream_results ---
async def aggregate_hour(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    bucket_start: datetime | None = None,
) -> dict[str, Any]:
    await ensure_analytics_schema(pool)
    start = bucket_start or datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)

    stats = await pool.fetchrow(
        """
        SELECT
          COUNT(*)::bigint AS total_requests,
          COALESCE(AVG(score), 0)::float AS avg_score,
          COUNT(*) FILTER (WHERE is_anomaly)::int AS anomaly_count
        FROM stream_results
        WHERE tenant_id = $1::uuid
          AND created_at >= $2 AND created_at < $3
        """,
        str(tenant_id),
        start,
        end,
    )
    threats = await pool.fetchval(
        """
        SELECT COUNT(*)::int FROM threat_intelligence
        WHERE (tenant_id = $1::uuid OR is_platform = TRUE)
          AND created_at >= $2 AND created_at < $3
        """,
        str(tenant_id),
        start,
        end,
    )
    incidents = await pool.fetchval(
        """
        SELECT COUNT(*)::int FROM incident_cases
        WHERE tenant_id = $1::uuid
          AND status IN ('open', 'investigating')
          AND created_at >= $2 AND created_at < $3
        """,
        str(tenant_id),
        start,
        end,
    )
    total = int(stats["total_requests"] or 0)
    anomalies = int(stats["anomaly_count"] or 0)
    error_rate = (anomalies / total * 100.0) if total else 0.0
    # Approximate p99 from anomaly scores ordered
    scores = await pool.fetch(
        """
        SELECT score FROM stream_results
        WHERE tenant_id = $1::uuid AND created_at >= $2 AND created_at < $3
          AND score IS NOT NULL
        ORDER BY score ASC
        """,
        str(tenant_id),
        start,
        end,
    )
    p99 = 0.0
    if scores:
        idx = percentile_index(len(scores), 0.99)
        p99 = float(scores[min(idx, len(scores) - 1)]["score"] or 0) * 1000.0

    row = await pool.fetchrow(
        """
        INSERT INTO aggregated_analytics (
            tenant_id, bucket_start, bucket_size, total_requests, avg_latency_ms,
            p99_latency_ms, error_rate_percent, threats_detected, active_incidents, metadata
        )
        VALUES (
            $1::uuid, $2, '1h', $3, $4, $5, $6, $7, $8, $9::jsonb
        )
        ON CONFLICT (tenant_id, bucket_start, bucket_size) DO UPDATE SET
            total_requests = EXCLUDED.total_requests,
            avg_latency_ms = EXCLUDED.avg_latency_ms,
            p99_latency_ms = EXCLUDED.p99_latency_ms,
            error_rate_percent = EXCLUDED.error_rate_percent,
            threats_detected = EXCLUDED.threats_detected,
            active_incidents = EXCLUDED.active_incidents,
            metadata = EXCLUDED.metadata,
            updated_at = NOW()
        RETURNING id::text, tenant_id::text, bucket_start, total_requests,
                  avg_latency_ms, p99_latency_ms, error_rate_percent,
                  threats_detected, active_incidents
        """,
        str(tenant_id),
        start,
        total,
        float(stats["avg_score"] or 0) * 1000.0,
        p99,
        error_rate,
        int(threats or 0),
        int(incidents or 0),
        json.dumps({"source": "stream_results"}),
    )
    return {"ok": True, "bucket": dict(row)}


async def overview(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
) -> dict[str, Any]:
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    await ensure_analytics_schema(pool)
    since = datetime.now(UTC) - timedelta(hours=24)
    rollups = await pool.fetch(
        """
        SELECT total_requests, avg_latency_ms, p99_latency_ms, error_rate_percent,
               threats_detected, active_incidents
        FROM aggregated_analytics
        WHERE tenant_id = $1::uuid AND bucket_start >= $2
        ORDER BY bucket_start DESC
        """,
        str(tenant_id),
        since,
    )
    total_req = sum(int(r["total_requests"] or 0) for r in rollups)
    threats = sum(int(r["threats_detected"] or 0) for r in rollups)
    incidents = sum(int(r["active_incidents"] or 0) for r in rollups)
    p99 = max((float(r["p99_latency_ms"] or 0) for r in rollups), default=0.0)
    err_sum = sum(float(r["error_rate_percent"] or 0) for r in rollups)
    uptime = max(0.0, 100.0 - (err_sum / max(1, len(rollups))))
    ces = ces_composite(uptime_pct=uptime, incidents=incidents, p99_ms=p99)
    return {
        "ok": True,
        "window_hours": 24,
        "total_requests": total_req,
        "threats_detected": threats,
        "active_incidents": incidents,
        "p99_latency_ms": p99,
        "uptime_pct": uptime,
        "status": uptime_status(uptime / 100.0),
        "ces": ces,
    }
