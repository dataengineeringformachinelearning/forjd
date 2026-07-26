# ADR-0003: Rust streams, Polars batch, Python soft fallback

## Status

Accepted — 2026-07-26 (codifies stack map)

## Context

Streaming ingest needs low-latency, ciphertext-safe detectors. Batch analytics
needs DataFrames. Orchestration needs Python. Using one tool for all three
(Polars-as-stream, Pathway revival, Airflow) has been proposed and rejected for
complexity and security surface.

## Decision

| Concern | Owner |
|---------|--------|
| Continuous / incremental streams | Rust data plane (`forjd-engine`, `FORJD_ROLE`) |
| Sealed hot-path detectors | Rust `run_sealed_pipeline` (HTTP or PyO3) |
| Soft fallback when Rust unavailable | Dependency-free **Python** sealed rollup — not Polars |
| Finite batch tables / ETL / reports | **Polars** |
| Workflow orchestration | Prefect 3 + YAML under `backend/workflows/` |

Never use Polars as a substitute for streaming jobs. Never revive Pathway as the
production stream engine.

## Consequences

- Engine deploy is one binary/features set (`server` + `data-plane`)
- Python fallback preserves successful semantics under engine outage; it is not
  a second product path
- See `AGENTS.md` stack map; scale ideas in `docs/SCALE.md` stay deferred until
  catalogued (ADR-0004)
