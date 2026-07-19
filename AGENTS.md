# FORJD AGENTS.md

## Product

FORJD is a universal secure streaming engine with configurable workflows.
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
| Engine | Rust (`engine/`) — one `forjd-engine` binary: Arrow/Parquet **59** + PyO3 + axum process HTTP + data plane (`FORJD_ROLE`, Postgres outbox, Dragonfly Streams) |
| Cache / DB | Dragonfly (Fly.io) + Postgres (Supabase) |
| UI | Angular + forjd-ui (Storybook / Chromatic) |
| Observability | Rollbar (API); Vercel Analytics + Speed Insights (frontend) |
| ML (optional) | `/api/v1/ml` catalog + Supabase `training_runs` / `embedding_vectors` / `ml_scores` (`sql/016`); hydrate from `stream_results` metadata only (`uv sync --group ml`) |
| Auth / E2EE | Supabase Auth **user** JWTs + tenant-scoped **service accounts** (`sql/014`–`015`, `017`–`018`, `backend/docs/AUTH.md`); X25519/HKDF + AES-256-GCM sealed ingest (`sql/003`–`008`, `013`); partner erase `POST /api/v1/tenants/{id}/erase` |
| Workflows | YAML under `backend/workflows/` → Prefect + **Rust sealed pipeline** (Pathway fallback) + pluggable detectors |
| Projections | Checkpointed durable `stream_results` + replay/DLQ (`/api/v1/projections`, `/api/v1/replay`) |
| Status | Tenant status pages (`/api/v1/status`) — public when published |
| Audit | Metadata-only `audit_events` (`sql/010`) — never ciphertext/keys |
| Domain security | Threat intel, SOC, playbooks, exports, ML, scanners (`sql/011`–`012`) — tenant-scoped |
| Edge | Supabase Edge Functions under `supabase/functions/` (e.g. `peer-sessions`) |

**Architecture:** see root `ARCHITECTURE.md`. Supabase provides Auth, Postgres, pgvector, and Realtime.

Partner apps are **subprocessors**: they keep their own end-user auth (e.g. Firebase) and call FORJD with a tenant-bound service token — never with end-user tokens.
Rust owns the hot-path sealed pipeline (`/v1/sealed/pipeline`, PyO3 `run_sealed_pipeline`) and data-plane roles.
Pathway is soft-fallback for sealed rollups; Polars owns finite batch DataFrames.
Backend Python is pinned to **3.12** with Pathway ≥0.31 (`beartype<0.16` via uv override).

## How to work

- Small, testable increments. Do not expand scope beyond what was asked.
- Prefer configuration (YAML/JSON) over hardcoding.
- Keep dependencies minimal — add a package only when a concrete use case needs it.
- After meaningful progress, append a `LOG.MD` entry (format in `.cursorrules`).

Last updated: 2026-07-18

**Deploy:** [`docs/PRODUCTION_DEPLOY.md`](docs/PRODUCTION_DEPLOY.md) + [`docs/PRODUCTION_CHECKLIST.md`](docs/PRODUCTION_CHECKLIST.md) — SQL `003`–`019`, mint `fjsvc_`, Fly backend/engine + Vercel frontend. Partners integrate via YAML workflows and tenant-bound service tokens.

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
