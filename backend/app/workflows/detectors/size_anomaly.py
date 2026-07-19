"""Cipher-length z-score / hard-max detector (E2EE-safe)."""

from __future__ import annotations

import math
import statistics
from typing import Any


# --- Size outlier detection ---
def detect(events: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    if not events:
        return []
    z_thresh = float(params.get("zscore", 2.5))
    max_len = int(params.get("max_cipher_len", 262_144))
    lengths = [int(e.get("cipher_len") or 0) for e in events]
    mean = statistics.fmean(lengths)
    std = statistics.pstdev(lengths) if len(lengths) > 1 else 0.0

    out: list[dict[str, Any]] = []
    for e in events:
        clen = int(e.get("cipher_len") or 0)
        z = 0.0 if std < 1e-9 else (clen - mean) / std
        hard = clen >= max_len
        spike = abs(z) >= z_thresh and std >= 1e-9
        is_anom = hard or spike
        score = abs(z) if std >= 1e-9 else (1.0 if hard else 0.0)
        if hard:
            score = max(score, float(clen) / float(max_len))
        out.append(
            {
                "event_id": str(e.get("event_id") or ""),
                "tenant_id": str(e.get("tenant_id") or ""),
                "key_id": str(e.get("key_id") or ""),
                "cipher_len": clen,
                "z_score": round(z, 4) if math.isfinite(z) else 0.0,
                "score": round(score, 4),
                "is_anomaly": is_anom,
                "detector": "size_anomaly",
                "reason": ("max_cipher_len" if hard else ("z_score" if spike else "ok")),
            }
        )
    return out
