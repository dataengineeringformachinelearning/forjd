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

    Soft-fails on import/runtime errors so other pulse layers still return.
    Backend targets CPython 3.12 with Pathway >=0.31 (beartype<0.16).
    """
    try:
        import pandas as pd
        import pathway as pw
    except Exception as exc:  # pragma: no cover
        logger.warning("pathway unavailable: %s", exc)
        return {
            "ok": False,
            "error": str(exc),
            "note": "Pathway import failed. Backend should run on CPython 3.12 + pathway>=0.31.",
        }

    if not values:
        return {"ok": False, "error": "values must not be empty"}

    try:
        table = pw.debug.table_from_pandas(pd.DataFrame({"value": values}))
        reduced = table.reduce(
            count=pw.reducers.count(),
            total=pw.reducers.sum(pw.this.value),
        )
        frame = pw.debug.table_to_pandas(reduced)
        count = int(frame["count"].iloc[0])
        total = float(frame["total"].iloc[0])
        return {
            "ok": True,
            "count": count,
            "total": total,
            "mean": (total / count) if count else 0.0,
        }
    except Exception as exc:
        logger.exception("pathway pulse failed")
        return {"ok": False, "error": str(exc)}
