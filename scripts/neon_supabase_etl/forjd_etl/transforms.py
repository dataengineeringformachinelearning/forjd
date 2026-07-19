"""Row-level field transforms and vector validation."""

from __future__ import annotations

import json
from typing import Any

from forjd_etl.config import TableSpec, TransformSpec, VectorColumn


# --- Column selection ---
def resolve_column_map(
    source_columns: list[str],
    spec: TableSpec,
) -> dict[str, str]:
    """Return mapping source_col → target_col."""
    exclude = set(spec.exclude_columns)
    if spec.columns:
        out: dict[str, str] = {}
        for src, dst in spec.columns.items():
            if src in exclude:
                continue
            if src not in source_columns:
                raise ValueError(f"mapped source column {src!r} not on {spec.source}")
            out[src] = dst
        return out
    return {c: c for c in source_columns if c not in exclude}


# --- Transforms ---
def apply_transforms(
    row: dict[str, Any],
    transforms: list[TransformSpec],
    *,
    column_map: dict[str, str],
) -> dict[str, Any]:
    """Apply transforms keyed by *source* column name; mutate mapped target keys."""
    out = dict(row)
    # Work in source-key space first
    for t in transforms:
        if t.column not in out:
            continue
        out[t.column] = _apply_one(out[t.column], t)
    # Remap to target keys
    mapped: dict[str, Any] = {}
    for src, dst in column_map.items():
        if src in out:
            mapped[dst] = out[src]
    return mapped


def _apply_one(value: Any, t: TransformSpec) -> Any:
    op = t.op.lower()
    if op in {"identity", "none", ""}:
        return value
    if value is None:
        return None
    if op == "strip":
        return str(value).strip()
    if op == "lower":
        return str(value).lower()
    if op == "upper":
        return str(value).upper()
    if op == "map":
        key = str(value)
        return t.map.get(key, t.map.get(value, value))
    if op == "const":
        return t.value
    if op == "json_dumps":
        return json.dumps(value) if not isinstance(value, str) else value
    if op == "null_if_empty":
        if value == "" or value == [] or value == {}:
            return None
        return value
    raise ValueError(f"unknown transform op: {t.op!r}")


# --- pgvector ---
def validate_vector_cell(
    value: Any,
    col: VectorColumn,
) -> Any:
    """Normalize / validate a vector value; raise ValueError on hard failures."""
    if value is None:
        return None
    dims = col.dimensions
    if isinstance(value, str):
        # Postgres vector text form: [1,2,3]
        text = value.strip()
        if dims is not None and text.startswith("[") and text.endswith("]"):
            parts = [p for p in text[1:-1].split(",") if p.strip()]
            if len(parts) != dims:
                raise ValueError(f"vector {col.name}: expected {dims} dims, got {len(parts)}")
        return value
    if isinstance(value, (list, tuple)):
        if dims is not None and len(value) != dims:
            raise ValueError(f"vector {col.name}: expected {dims} dims, got {len(value)}")
        return "[" + ",".join(str(float(x)) for x in value) + "]"
    return value


def apply_vector_validation(
    row: dict[str, Any],
    vector_columns: list[VectorColumn],
    *,
    column_map: dict[str, str],
) -> dict[str, Any]:
    src_by_target = {dst: src for src, dst in column_map.items()}
    out = dict(row)
    for vc in vector_columns:
        # Config names source column; after map it may be renamed
        target_name = column_map.get(vc.name, vc.name)
        if target_name not in out and vc.name in out:
            target_name = vc.name
        if target_name not in out:
            # Try original source key still present
            src = src_by_target.get(vc.name, vc.name)
            if src in out:
                out[src] = validate_vector_cell(out[src], vc)
            continue
        out[target_name] = validate_vector_cell(out[target_name], vc)
    return out
