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
    if ratio >= 0.99:
        return "degraded"
    if ratio >= 0.95:
        return "partial_outage"
    return "major_outage"


# --- Routing-tag distribution helpers (sealed metadata only) ---
def _top_counts(counts: dict[str, int], *, limit: int = 12) -> list[dict[str, Any]]:
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
    return [{"name": name, "count": count} for name, count in ranked if count > 0]


async def _routing_distributions(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Bucket sealed routing tags for partner charts (never plaintext payloads)."""
    rows = await pool.fetch(
        """
        SELECT
          NULLIF(BTRIM(metadata->>'region'), '') AS region,
          NULLIF(BTRIM(metadata->>'component'), '') AS component,
          NULLIF(BTRIM(metadata->>'label'), '') AS label,
          NULLIF(BTRIM(metadata->>'source'), '') AS source,
          NULLIF(BTRIM(features->>'key_id'), '') AS key_id
        FROM stream_results
        WHERE tenant_id = $1::uuid
          AND created_at >= $2 AND created_at < $3
        """,
        str(tenant_id),
        start,
        end,
    )
    regions: dict[str, int] = {}
    components: dict[str, int] = {}
    statuses: dict[str, int] = {}
    visitors: set[str] = set()
    for row in rows:
        region = str(row["region"] or row["source"] or "").strip()
        if region:
            regions[region] = regions.get(region, 0) + 1
        component = str(row["component"] or "").strip()
        if component:
            components[component] = components.get(component, 0) + 1
        label = str(row["label"] or "").strip().lower()
        if label in {"1xx", "2xx", "3xx", "4xx", "5xx"} or label.isdigit():
            statuses[label] = statuses.get(label, 0) + 1
        key_id = str(row["key_id"] or "").strip()
        if key_id:
            visitors.add(key_id)
    return {
        "unique_visitors": len(visitors),
        "origin_distribution": [
            {"region": item["name"], "count": item["count"]} for item in _top_counts(regions)
        ],
        "endpoint_counts": [
            {"endpoint": item["name"], "count": item["count"]} for item in _top_counts(components)
        ],
        "http_statuses": [
            {"status": item["name"], "count": item["count"]} for item in _top_counts(statuses)
        ],
    }


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
    distributions = await _routing_distributions(pool, tenant_id=tenant_id, start=start, end=end)
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

    bucket_metadata = {
        "source": "stream_results",
        "origin_distribution": distributions["origin_distribution"],
        "endpoint_counts": distributions["endpoint_counts"],
        "http_statuses": distributions["http_statuses"],
    }
    row = await pool.fetchrow(
        """
        INSERT INTO aggregated_analytics (
            tenant_id, bucket_start, bucket_size, total_requests, avg_latency_ms,
            p99_latency_ms, error_rate_percent, threats_detected, active_incidents,
            unique_visitors, metadata
        )
        VALUES (
            $1::uuid, $2, '1h', $3, $4, $5, $6, $7, $8, $9, $10::jsonb
        )
        ON CONFLICT (tenant_id, bucket_start, bucket_size) DO UPDATE SET
            total_requests = EXCLUDED.total_requests,
            avg_latency_ms = EXCLUDED.avg_latency_ms,
            p99_latency_ms = EXCLUDED.p99_latency_ms,
            error_rate_percent = EXCLUDED.error_rate_percent,
            threats_detected = EXCLUDED.threats_detected,
            active_incidents = EXCLUDED.active_incidents,
            unique_visitors = EXCLUDED.unique_visitors,
            metadata = EXCLUDED.metadata,
            updated_at = NOW()
        RETURNING id::text, tenant_id::text, bucket_start, total_requests,
                  avg_latency_ms, p99_latency_ms, error_rate_percent,
                  threats_detected, active_incidents, unique_visitors
        """,
        str(tenant_id),
        start,
        total,
        float(stats["avg_score"] or 0) * 1000.0,
        p99,
        error_rate,
        int(threats or 0),
        int(incidents or 0),
        int(distributions["unique_visitors"] or 0),
        json.dumps(bucket_metadata),
    )
    return {"ok": True, "bucket": dict(row)}


# --- Overview series helpers ---
def _bucket_label(bucket_start: Any) -> str:
    if hasattr(bucket_start, "strftime"):
        return bucket_start.strftime("%H:%M")
    text = str(bucket_start or "")
    return text[11:16] if len(text) >= 16 else text


def _spiking_temporal_forecast(rollups: list[Any]) -> float:
    """Simple half-window spike score from threats + error rate (0–100).

    Expects newest-first rollup rows (matching overview SQL order).
    """
    if len(rollups) < 2:
        return 0.0
    chronological = list(reversed(rollups))
    mid = max(1, len(chronological) // 2)
    older, newer = chronological[:mid], chronological[mid:]

    def _pressure(rows: list[Any]) -> float:
        if not rows:
            return 0.0
        threats = sum(int(r["threats_detected"] or 0) for r in rows) / len(rows)
        errors = sum(float(r["error_rate_percent"] or 0) for r in rows) / len(rows)
        return threats * 10.0 + errors

    older_p = _pressure(older)
    newer_p = _pressure(newer)
    if older_p <= 0 and newer_p <= 0:
        return 0.0
    delta = max(0.0, newer_p - older_p)
    baseline = max(older_p, 1.0)
    return round(min(100.0, (newer_p / baseline) * 40.0 + delta * 2.0), 1)


async def overview(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        required_scopes=frozenset({"analytics:read"}),
    )
    await ensure_analytics_schema(pool)
    since = datetime.now(UTC) - timedelta(hours=24)
    rollups = await pool.fetch(
        """
        SELECT bucket_start, total_requests, avg_latency_ms, p99_latency_ms,
               error_rate_percent, threats_detected, active_incidents, unique_visitors,
               metadata
        FROM aggregated_analytics
        WHERE tenant_id = $1::uuid AND bucket_start >= $2
        ORDER BY bucket_start DESC
        """,
        str(tenant_id),
        since,
    )
    # --- Stale-window fallback ---
    # Rollups only tick for tenants with fresh stream_results. When the 24h
    # window is empty, surface the most recent buckets so partner dashboards
    # still show CES/series instead of a blank page after quiet periods.
    window_hours = 24
    if not rollups:
        rollups = await pool.fetch(
            """
            SELECT bucket_start, total_requests, avg_latency_ms, p99_latency_ms,
                   error_rate_percent, threats_detected, active_incidents, unique_visitors,
                   metadata
            FROM aggregated_analytics
            WHERE tenant_id = $1::uuid
            ORDER BY bucket_start DESC
            LIMIT 24
            """,
            str(tenant_id),
        )
        if rollups:
            newest = rollups[0]["bucket_start"]
            oldest = rollups[-1]["bucket_start"]
            if newest is not None and oldest is not None:
                try:
                    window_hours = max(
                        1,
                        int((newest - oldest).total_seconds() // 3600) + 1,
                    )
                except (TypeError, AttributeError):
                    window_hours = 24
    total_req = sum(int(r["total_requests"] or 0) for r in rollups)
    threats = sum(int(r["threats_detected"] or 0) for r in rollups)
    incidents = sum(int(r["active_incidents"] or 0) for r in rollups)
    visitors = sum(int(r["unique_visitors"] or 0) for r in rollups)
    p99 = max((float(r["p99_latency_ms"] or 0) for r in rollups), default=0.0)

    # No rollups ⇒ unknown availability (never invent 100% uptime / healthy CES).
    if not rollups:
        return {
            "ok": True,
            "window_hours": 24,
            "total_requests": 0,
            "threats_detected": 0,
            "active_incidents": 0,
            "unique_visitors": 0,
            "p99_latency_ms": 0.0,
            "uptime_pct": None,
            "status": "unknown",
            "data_available": False,
            "ces": {
                "ces_threat": 0.0,
                "ces_sla": 0.0,
                "ces_stability": 0.0,
                "ces_level": 0.0,
                "spiking_temporal_forecast": 0.0,
            },
            "time_series": [],
            "uptime_series": [],
            "threat_series": [],
            "threat_severity": [],
            "origin_distribution": [],
            "http_statuses": [],
            "endpoint_counts": [],
        }

    err_sum = sum(float(r["error_rate_percent"] or 0) for r in rollups)
    uptime = max(0.0, 100.0 - (err_sum / len(rollups)))
    ces = ces_composite(uptime_pct=uptime, incidents=incidents, p99_ms=p99)

    # --- Chronological series for partner dashboards (oldest → newest) ---
    chronological = list(reversed(rollups))
    time_series: list[dict[str, Any]] = []
    uptime_series: list[dict[str, Any]] = []
    threat_series: list[dict[str, Any]] = []
    for row in chronological:
        label = _bucket_label(row["bucket_start"])
        bucket_uptime = max(0.0, 100.0 - float(row["error_rate_percent"] or 0))
        time_series.append(
            {
                "label": label,
                "time": label,
                "latency": float(row["p99_latency_ms"] or 0),
                "requests": int(row["total_requests"] or 0),
            }
        )
        uptime_series.append({"label": label, "time": label, "uptime": bucket_uptime})
        threat_series.append(
            {
                "label": label,
                "time": label,
                "count": int(row["threats_detected"] or 0),
            }
        )

    threat_severity: list[dict[str, Any]] = []
    if threats > 0:
        threat_severity.append({"severity": "Detected", "count": threats})

    # --- Merge per-bucket routing-tag charts for partner dashboards ---
    origin_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    endpoint_counts: dict[str, int] = {}
    for row in rollups:
        meta = row["metadata"]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        if not isinstance(meta, dict):
            continue
        for item in meta.get("origin_distribution") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("region") or item.get("name") or "").strip()
            if name:
                origin_counts[name] = origin_counts.get(name, 0) + int(item.get("count") or 0)
        for item in meta.get("http_statuses") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("status") or item.get("name") or "").strip()
            if name:
                status_counts[name] = status_counts.get(name, 0) + int(item.get("count") or 0)
        for item in meta.get("endpoint_counts") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("endpoint") or item.get("name") or "").strip()
            if name:
                endpoint_counts[name] = endpoint_counts.get(name, 0) + int(item.get("count") or 0)

    return {
        "ok": True,
        "window_hours": window_hours,
        "total_requests": total_req,
        "threats_detected": threats,
        "active_incidents": incidents,
        "unique_visitors": visitors,
        "p99_latency_ms": p99,
        "uptime_pct": uptime,
        "status": uptime_status(uptime / 100.0),
        "data_available": True,
        "ces": {
            **ces,
            "spiking_temporal_forecast": _spiking_temporal_forecast(list(rollups)),
        },
        "time_series": time_series,
        "uptime_series": uptime_series,
        "threat_series": threat_series,
        "threat_severity": threat_severity,
        "origin_distribution": [
            {"region": item["name"], "count": item["count"]} for item in _top_counts(origin_counts)
        ],
        "http_statuses": [
            {"status": item["name"], "count": item["count"]} for item in _top_counts(status_counts)
        ],
        "endpoint_counts": [
            {"endpoint": item["name"], "count": item["count"]}
            for item in _top_counts(endpoint_counts)
        ],
    }
