"""Pathway consumer for sealed telemetry metadata (server-blind).

Operates only on non-sensitive fields: tenant_id, key_id, content_type, sizes.
Never decrypts ciphertext — that stays on the E2EE client path.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("forjd.stream")


def pathway_sealed_rollup(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Finite Pathway reduce over sealed-event metadata for the ingest PoC.

    Soft-fails when Pathway is unavailable (same pattern as pulse).
    """
    if not events:
        return {"ok": True, "count": 0, "tenants": 0, "by_tenant": {}}

    try:
        import pandas as pd
        import pathway as pw
    except Exception as exc:  # pragma: no cover
        logger.warning("pathway unavailable: %s", exc)
        return _python_rollup(events, error=str(exc))

    rows = []
    for e in events:
        rows.append(
            {
                "tenant_id": str(e.get("tenant_id", "")),
                "key_id": str(e.get("key_id", "")),
                "cipher_len": int(e.get("cipher_len") or 0),
            }
        )

    try:
        table = pw.debug.table_from_pandas(pd.DataFrame(rows))
        reduced = table.groupby(pw.this.tenant_id).reduce(
            tenant_id=pw.this.tenant_id,
            count=pw.reducers.count(),
            bytes=pw.reducers.sum(pw.this.cipher_len),
        )
        frame = pw.debug.table_to_pandas(reduced)
        by_tenant: dict[str, Any] = {}
        for _, row in frame.iterrows():
            by_tenant[str(row["tenant_id"])] = {
                "count": int(row["count"]),
                "bytes": int(row["bytes"]),
            }
        return {
            "ok": True,
            "engine": "pathway",
            "count": sum(v["count"] for v in by_tenant.values()),
            "tenants": len(by_tenant),
            "by_tenant": by_tenant,
        }
    except Exception as exc:
        logger.exception("pathway sealed rollup failed")
        return _python_rollup(events, error=str(exc))


def _python_rollup(events: list[dict[str, Any]], *, error: str | None = None) -> dict[str, Any]:
    by_tenant: dict[str, dict[str, int]] = {}
    for e in events:
        tid = str(e.get("tenant_id", ""))
        slot = by_tenant.setdefault(tid, {"count": 0, "bytes": 0})
        slot["count"] += 1
        slot["bytes"] += int(e.get("cipher_len") or 0)
    out: dict[str, Any] = {
        "ok": error is None,
        "engine": "python-fallback",
        "count": len(events),
        "tenants": len(by_tenant),
        "by_tenant": by_tenant,
    }
    if error:
        out["error"] = error
    return out
