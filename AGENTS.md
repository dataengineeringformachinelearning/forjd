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

Pathway owns live/incremental work; Polars owns finite batch DataFrames. Details: `.cursorrules`.
Note: Pathway currently fails to import on CPython 3.14 — the pulse PoC soft-fails that layer.

## How to work
- Small, testable increments. Do not expand scope beyond what was asked.
- Prefer configuration (YAML/JSON) over hardcoding.
- Keep dependencies minimal — add a package only when a concrete use case needs it.
- After meaningful progress, append a `LOG.MD` entry (format in `.cursorrules`).

Last updated: 2026-07-16

## Cursor Cloud specific instructions

The startup update script runs `uv sync --project backend` (also builds the Rust
engine via maturin/PyO3) and `npm install --prefix frontend`. Toolchain (`uv`,
Python 3.14, Rust 1.97 via `rust-toolchain.toml`, Node via nvm, native Postgres +
Redis) is baked into the VM image. Standard per-component commands live in the
root `README.md` and each subdir README — use those; notes below are only the
non-obvious caveats.

### Node version gotcha (important)
`/exec-daemon/node` is pinned to v22.14.0, which is **too old** for the Angular 22
CLI (needs ≥ v22.22.3). A newer Node (v24) is installed via nvm and prepended to
`PATH` in `~/.bashrc`, so interactive shells and tmux login shells get it
automatically. If a build fails with "Angular CLI requires a minimum Node.js
version", ensure `$HOME/.nvm/versions/node/v24.18.0/bin` is ahead of
`/exec-daemon` on `PATH`.

### Backing services (native, not Docker)
Postgres and Redis run as native processes (no Docker in this VM). They do **not**
auto-start on boot — start them each session before running the API:
```bash
sudo pg_ctlcluster 16 main start                                   # Postgres :5432 (db forjd, postgres/postgres)
sudo redis-server --daemonize yes --requirepass forjd-dev-local --port 6379   # Redis :6379 (Dragonfly-compatible)
```
`backend/.env` (copied from `.env.example`) already points at these. Redis stands
in for Dragonfly (wire-compatible); the app reports it as `dragonfly`.

### Running the stack
- API: `cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Web: `cd frontend && npm start` (http://localhost:4200, dev build targets :8000)
- A pulse (`POST /api/v1/pulse` or the UI "Run pulse") reports **5/6 layers ok**:
  `engine`, `polars`, `postgres`, `dragonfly` ok; `prefect` ok via local-fallback
  (no Prefect server needed); `pathway` fails on CPython 3.14 (expected — see note
  above). This is the healthy steady state, not a regression.

### Frontend install scripts
`npm install` under npm 11 warns about ungated build scripts (esbuild/lmdb native
builds). The image ships a populated `frontend/node_modules`, so refresh installs
are fine; only a from-scratch `rm -rf node_modules` reinstall may need those build
scripts approved.

### Tests / lint (no scripted aliases)
- Backend lint: `uv run ruff check .` / `uv run ruff format --check .` (no pytest suite).
- Engine: `cargo test`, `cargo clippy --all-targets --all-features` (`cargo fmt --check` currently reports a pre-existing diff).
- Frontend: `npx ng test --no-watch` (Vitest + jsdom); no ESLint target, Prettier only.
