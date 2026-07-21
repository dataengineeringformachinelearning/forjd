"""Per-tenant event-count burst detector (E2EE-safe; operates on the current batch)."""

from __future__ import annotations

from collections import Counter
from typing import Any


# --- Rate / burst detection within the current batch ---
def detect(events: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    """Flag tenants that exceed max_events in this processing batch.

    Full sliding windows need continuous projectors; this baseline uses batch counts
    so YAML can enable threat-style rate signals without plaintext.
    """
    if not events:
        return []
    max_events = int(params.get("max_events", 500))
    counts = Counter(str(e.get("tenant_id") or "") for e in events)
    hot = {tid for tid, n in counts.items() if n >= max_events}

    out: list[dict[str, Any]] = []
    for e in events:
        tid = str(e.get("tenant_id") or "")
        n = counts[tid]
        is_anom = tid in hot
        score = float(n) / float(max_events) if max_events > 0 else 0.0
        out.append(
            {
                "event_id": str(e.get("event_id") or ""),
                "tenant_id": tid,
                "key_id": str(e.get("key_id") or ""),
                "cipher_len": int(e.get("cipher_len") or 0),
                "batch_count": n,
                "score": round(score, 4),
                "is_anomaly": is_anom,
                "detector": "rate_anomaly",
                "reason": "batch_rate" if is_anom else "ok",
            }
        )
    return out
