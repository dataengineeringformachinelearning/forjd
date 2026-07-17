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
| Engine | Rust (`engine/`) — tokio, Arrow/Parquet **59**, PyO3 → Python; axum HTTP on Fly/Compose (`ENGINE_URL`) |
| Cache / DB | Dragonfly (Fly.io) + Postgres (Supabase) |
| UI | Angular + forjd-ui (Storybook / Chromatic) |
| Observability | Rollbar (API); Vercel Analytics + Speed Insights (frontend) |
| ML (optional PoC) | PyTorch LSTM-AE (`uv sync --group ml`) + Supabase pgvector latents |
| Auth / E2EE | Supabase Auth JWT + X25519/HKDF session keys + AES-256-GCM sealed ingest (`sql/003` + `004`) |

Pathway owns live/incremental work; Polars owns finite batch DataFrames. Details: `.cursorrules`.
Backend Python is pinned to **3.12** with Pathway ≥0.31 (`beartype<0.16` via uv override). Pathway still does not support 3.14.

## How to work
- Small, testable increments. Do not expand scope beyond what was asked.
- Prefer configuration (YAML/JSON) over hardcoding.
- Keep dependencies minimal — add a package only when a concrete use case needs it.
- After meaningful progress, append a `LOG.MD` entry (format in `.cursorrules`).

Last updated: 2026-07-16
