# FORJD AGENTS.md

## Product
FORJD is a data streaming pipeline platform with configurable workflows.
Agents: read this briefing first, then enforce constraints in `.cursorrules`.

## Principles
- Stability and security over bleeding edge.
- Lightweight and observable.
- Precision over chance.
- Build for learning and long-term maintainability.

## Stack map
| Layer | Choice |
|-------|--------|
| API | FastAPI |
| Orchestration | Prefect 3 |
| Streams | Pathway |
| Batch tables | Polars |
| Engine | Rust (`engine/`) — tokio, Arrow/Parquet, PyO3 → Python |
| Cache / DB | Dragonfly (Fly.io) + Postgres (Supabase) |
| UI | Angular + forjd-ui (Storybook / Chromatic) |
| Observability | Rollbar (API); Vercel Analytics + Speed Insights (frontend) |

Pathway owns live/incremental work; Polars owns finite batch DataFrames. Details: `.cursorrules`.
Note: Pathway currently fails to import on CPython 3.14 — the pulse PoC soft-fails that layer.

## How to work
- Small, testable increments. Do not expand scope beyond what was asked.
- Prefer configuration (YAML/JSON) over hardcoding.
- Keep dependencies minimal — add a package only when a concrete use case needs it.
- After meaningful progress, append a `LOG.MD` entry (format in `.cursorrules`).

Last updated: 2026-07-15
