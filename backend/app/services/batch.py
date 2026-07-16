"""Batch (Polars) + stream (Pathway) helpers for the pulse PoC."""

from __future__ import annotations

import logging
from typing import Any

import polars as pl

logger = logging.getLogger("forjd.batch")


def polars_summary(values: list[float]) -> dict[str, Any]:
    """Finite batch aggregate — Polars owns this lane."""
    df = pl.DataFrame({"value": values})
    row = df.select(
        pl.len().alias("count"),
        pl.col("value").sum().alias("sum"),
        pl.col("value").mean().alias("mean"),
        pl.col("value").min().alias("min"),
        pl.col("value").max().alias("max"),
    ).to_dicts()[0]
    return {
        "count": int(row["count"]),
        "sum": float(row["sum"]),
        "mean": float(row["mean"]),
        "min": float(row["min"]),
        "max": float(row["max"]),
    }


def pathway_increment(values: list[float]) -> dict[str, Any]:
    """Finite Pathway reduce for the PoC.

    Pathway currently fails to import on CPython 3.14 (upstream schema/beartype).
    We soft-fail so the rest of the pulse still runs; swap Python or wait for a
    Pathway release that supports 3.14 to light this layer up.
    """
    try:
        import pathway as pw
    except Exception as exc:  # pragma: no cover
        logger.warning("pathway unavailable: %s", exc)
        return {
            "ok": False,
            "error": str(exc),
            "note": "Pathway import failed (often CPython 3.14). Other layers still run.",
        }

    if not values:
        return {"ok": False, "error": "values must not be empty"}

    try:
        # Prefer markdown helper — widely available across Pathway versions.
        lines = [" | value"] + [f" | {v}" for v in values]
        table = pw.debug.table_from_markdown("\n".join(lines))
        reduced = table.reduce(
            count=pw.reducers.count(),
            total=pw.reducers.sum(pw.this.value),
        )
        # Finite materialization for the HTTP PoC (Pathway is normally continuous).
        if hasattr(pw.debug, "table_to_dicts"):
            rows = pw.debug.table_to_dicts(reduced)
            first = next(iter(rows.values()), {})
            count = int(first.get("count", 0))
            total = float(first.get("total", 0.0))
        else:
            pw.debug.compute_and_print(reduced)
            count = len(values)
            total = float(sum(values))
        return {
            "ok": True,
            "count": count,
            "total": total,
            "mean": (total / count) if count else 0.0,
        }
    except Exception as exc:
        logger.exception("pathway pulse failed")
        return {"ok": False, "error": str(exc)}
