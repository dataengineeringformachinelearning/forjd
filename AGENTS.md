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
| Cache / DB | Dragonfly + Postgres |
| UI | Angular + forjd-ui (Storybook / Chromatic) |
| Observability | Rollbar (API); Vercel Analytics + Speed Insights (frontend) |

Pathway owns live/incremental work; Polars owns finite batch DataFrames. Details: `.cursorrules`.

## How to work
- Small, testable increments. Do not expand scope beyond what was asked.
- Prefer configuration (YAML/JSON) over hardcoding.
- Keep dependencies minimal — add a package only when a concrete use case needs it.
- After meaningful progress, append a `LOG.MD` entry (format in `.cursorrules`).

Last updated: 2026-07-14
