"""Load and validate YAML ETL configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# --- Data models ---
@dataclass(frozen=True)
class IncrementalSpec:
    column: str


@dataclass(frozen=True)
class VectorColumn:
    name: str
    dimensions: int | None = None


@dataclass(frozen=True)
class TransformSpec:
    column: str
    op: str
    map: dict[str, Any] = field(default_factory=dict)
    value: Any = None


@dataclass
class TableSpec:
    source: str
    target: str
    primary_key: list[str]
    enabled: bool = True
    incremental: IncrementalSpec | None = None
    filter: str | None = None
    columns: dict[str, str] | None = None
    exclude_columns: list[str] = field(default_factory=list)
    transforms: list[TransformSpec] = field(default_factory=list)
    vector_columns: list[VectorColumn] = field(default_factory=list)


@dataclass
class EtlConfig:
    version: int
    source_schema: str
    target_schema: str
    create_schema: bool
    state_table: str
    extensions: list[str]
    batch_size: int
    max_retries: int
    retry_backoff_seconds: float
    mode: str
    dry_run: bool
    max_table_errors: int
    ensure_tables: bool
    ensure_columns: bool
    params: dict[str, Any]
    tables: list[TableSpec]


# --- Loaders ---
def load_config(path: Path | str) -> EtlConfig:
    raw_path = Path(path)
    data = yaml.safe_load(raw_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config root must be a mapping")
    return parse_config(data)


def parse_config(data: dict[str, Any]) -> EtlConfig:
    source = data.get("source") or {}
    target = data.get("target") or {}
    options = data.get("options") or {}
    mode = str(options.get("mode") or "full").strip().lower()
    if mode not in {"full", "incremental"}:
        raise ValueError("options.mode must be 'full' or 'incremental'")

    tables: list[TableSpec] = []
    for item in data.get("tables") or []:
        if not isinstance(item, dict):
            raise ValueError("each tables[] entry must be a mapping")
        pk = item.get("primary_key") or ["id"]
        if isinstance(pk, str):
            pk = [pk]
        inc_raw = item.get("incremental")
        incremental = None
        if isinstance(inc_raw, dict) and inc_raw.get("column"):
            incremental = IncrementalSpec(column=str(inc_raw["column"]))
        cols = item.get("columns")
        if cols is not None and not isinstance(cols, dict):
            raise ValueError(f"table {item.get('source')}: columns must be a mapping")
        transforms: list[TransformSpec] = []
        for t in item.get("transforms") or []:
            transforms.append(
                TransformSpec(
                    column=str(t["column"]),
                    op=str(t.get("op") or t.get("type") or "identity"),
                    map=dict(t.get("map") or {}),
                    value=t.get("value"),
                )
            )
        vectors: list[VectorColumn] = []
        for v in item.get("vector_columns") or []:
            vectors.append(
                VectorColumn(
                    name=str(v["name"]),
                    dimensions=int(v["dimensions"]) if v.get("dimensions") is not None else None,
                )
            )
        tables.append(
            TableSpec(
                source=str(item["source"]),
                target=str(item.get("target") or item["source"]),
                primary_key=[str(p) for p in pk],
                enabled=bool(item.get("enabled", True)),
                incremental=incremental,
                filter=item.get("filter"),
                columns=dict(cols) if cols else None,
                exclude_columns=[str(c) for c in (item.get("exclude_columns") or [])],
                transforms=transforms,
                vector_columns=vectors,
            )
        )

    target_schema = str(target.get("schema") or "partner_control")
    if target_schema == "public":
        raise ValueError(
            "target.schema must not be 'public' — "
            "FORJD data plane owns public (use partner_control)"
        )

    return EtlConfig(
        version=int(data.get("version") or 1),
        source_schema=str(source.get("schema") or "public"),
        target_schema=target_schema,
        create_schema=bool(target.get("create_schema", True)),
        state_table=str(target.get("state_table") or "_etl_checkpoints"),
        extensions=[str(e) for e in (data.get("extensions") or ["pgcrypto", "vector"])],
        batch_size=max(1, int(options.get("batch_size") or 1000)),
        max_retries=max(0, int(options.get("max_retries") or 5)),
        retry_backoff_seconds=float(options.get("retry_backoff_seconds") or 2.0),
        mode=mode,
        dry_run=bool(options.get("dry_run", False)),
        max_table_errors=max(0, int(options.get("max_table_errors") or 0)),
        ensure_tables=bool(options.get("ensure_tables", True)),
        ensure_columns=bool(options.get("ensure_columns", True)),
        params=dict(data.get("params") or {}),
        tables=tables,
    )
