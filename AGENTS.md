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
| Streams | Rust data plane + dependency-free Python fallback |
| Batch tables | Polars |
| Engine | Rust (`engine/`) — one `forjd-engine` binary: Arrow/Parquet **59** + PyO3 + axum process HTTP + data plane (`FORJD_ROLE`, Postgres outbox, Dragonfly Streams) |
| Cache / DB | Dragonfly (Fly.io) + Postgres (Supabase) |
| UI | Angular static FJORD landing + forjd-ui adapter (Storybook / Chromatic); suite-locked to DEML Viking-UI — [docs/SUITE_UI_UNIFICATION.md](docs/SUITE_UI_UNIFICATION.md); no product console |
| Observability | Structured JSON logs + `X-Request-ID` correlation; Rollbar (API + browser) + optional Sentry (`SENTRY_DSN`, `uv sync --group sentry`); Vercel Analytics + Speed Insights (frontend). Contract: [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md) |
| Configuration | Inventory SoT [`config/forjd.catalog.yaml`](config/forjd.catalog.yaml) + [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md); runtime SoT `Settings` / engine env / `environment*.ts`; flags via `app/core/feature_flags.py` |
| Rate limiting | Config-gated Dragonfly/Redis limiter (`app/core/rate_limit.py`; `RATE_LIMIT_ENABLED` + per-bucket RPM) |
| Add-ons (optional) | Config-gated integrations under `app/addons/` — disabled by default, `FORJD_ADDONS=<slug,…>` or `all`; catalog at `GET /api/v1/addons` (OSV/nuclei/HoneyDB/CVE + ML/testing descriptors) |
| External fetchers | Typed TET pipeline under `app/services/fetchers/` (query → extract → transform + `FetchResult`); OSINT/HIBP use it — no OpenBB/pandas finance stack |
| ML (optional) | `/api/v1/ml` catalog + Supabase `training_runs` / `embedding_vectors` / `ml_scores` (`sql/016`); hydrate from `stream_results` metadata only (`uv sync --group ml`) |
| Auth / E2EE | Supabase Auth **user** JWTs + tenant-scoped **service accounts** (`sql/014`–`015`, `017`–`018`, `backend/docs/AUTH.md`); X25519/HKDF + AES-256-GCM sealed ingest (`sql/003`–`008`, `013`); partner erase `POST /api/v1/tenants/{id}/erase`; headless SIEM/SOAR (`sql/020`, `025`) |
| Workflows | YAML under `backend/workflows/` → Prefect + **Rust sealed pipeline** (pure-Python fallback) + pluggable detectors |
| Projections | Checkpointed durable `stream_results` + replay/DLQ (`/api/v1/projections`, `/api/v1/replay`) |
| Rollups / ML refresh | Supervised `analytics-rollup` worker — hourly `aggregated_analytics` upserts + throttled `classical_anomaly` `ml_scores` refresh (`ANALYTICS_ROLLUP_INTERVAL_SECONDS`) |
| Scheduled training | Supervised `ml-training` worker — daily SLA/threat plus real-telemetry NorseSSN fit+score per active tenant (`TRAINING_*`), persisted to `training_runs`/`ml_scores`; optional Hugging Face publish (`HF_MODEL_REPO_ID` + `HF_TOKEN`, hashed tenant paths) |
| Data retention | Supervised `retention` worker — bounded deletes for aged `telemetry_events`/`stream_results`, expired `crypto_sessions`, completed ingest receipts (`RETENTION_*`) |
| Reports / exports / ingest durability | Report documents (`sql/022`); durable exports (`sql/023`); durable ingest-processing receipts (`sql/024`) |
| Status | Tenant status pages (`/api/v1/status`) — public when published |
| Audit | Metadata-only `audit_events` (`sql/010`) — never ciphertext/keys |
| Domain security | Threat intel, SOC, playbooks, exports, ML, scanners (`sql/011`–`012`); headless SIEM/SOAR signals/cases/playbook runs (`sql/020`, `025`) — tenant-scoped |
| Edge | Supabase Edge Functions under `supabase/functions/` (e.g. `peer-sessions`) |

**Architecture:** see root `ARCHITECTURE.md`. Supabase provides Auth, Postgres, pgvector, and Realtime.

Partner apps are **subprocessors**: they keep their own end-user auth (e.g. Firebase) and call FORJD with a tenant-bound service token — never with end-user tokens.
Rust owns the hot-path sealed pipeline (`/v1/sealed/pipeline`, PyO3 `run_sealed_pipeline`) and data-plane roles.
Dependency-free Python is the soft-fallback for sealed rollups; Polars owns finite batch DataFrames.
Backend Python is pinned to **3.12** for stable, reproducible production builds.

## How to work

- **First run:** [`docs/START_HERE.md`](docs/START_HERE.md) — `npm run bootstrap` → `dev:api` / `dev:web` → `npm run verify` (≈10 minutes of attention).
- **Extend / configure:** [`docs/EXTENDING.md`](docs/EXTENDING.md) — YAML workflows, detectors, add-ons; `npm run validate:workflows` before deploy.
- Small, testable increments. Do not expand scope beyond what was asked.
- Prefer configuration (YAML/JSON) over hardcoding.
- Keep dependencies minimal — add a package only when a concrete use case needs it.
- **Commits:** Conventional Commits + squash-merge practice — [`docs/GIT.md`](docs/GIT.md). `commit-msg` hook via `npm run install-hooks`.
- After meaningful progress, optionally append a `LOG.MD` entry (engineering journal — see `.cursorrules`); primary architecture docs are `ARCHITECTURE.md` and `AGENTS.md`.
- **Non-obvious patterns:** record or cite an ADR under [`docs/adr/`](docs/adr/README.md) instead of re-arguing rejected stacks (second rate limiter, Polars-as-stream, partner end-user tokens, second design system, premature APM).
- **Suite UI law:** chrome on forjd.co / backend.forjd.co must match deml.app / marketing (public Storybook hosts retired). Own every class; no Material/Bootstrap look packages. **Pass 1 tokens:** vendored `suite-tokens.css` (`--suite-*`; `--fj-*` aliases). No npm install for styles — `npm run sync:suite` from DEML sibling. Expand primitives in `frontend/libs/forjd-ui/` first.

## Quality gates

- First clone: `npm run bootstrap` · prove API: `npm run verify` ([`docs/START_HERE.md`](docs/START_HERE.md))
- Hooks: `npm run install-hooks` (`.pre-commit-config.yaml` — pre-commit + commit-msg)
- Meta: `npm run quality` / `npm run quality:full` (`scripts/forjd_tooling.py`)
- Workflows: `npm run validate:workflows` (CI also runs `--include-examples`)
- Backend: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run python -m unittest discover -s tests`
- Config catalog: `uv run --project backend python scripts/check_config_catalog.py`
- Engine: `cd engine && cargo fmt --all -- --check && cargo clippy --no-default-features --features server,data-plane -- -D warnings && cargo test --no-default-features --features server,data-plane`
- Frontend: `cd frontend && npm run format:check && npm run typecheck && npm run test:all && npm run build`
- CI: `.github/workflows/ci.yml` (backend + engine + frontend)
- Security: Semgrep (Cursor rule), no secrets in git, `rate_limit.py` is the sole rate limiter

Last updated: 2026-07-26

**Deploy:** [`docs/PRODUCTION_DEPLOY.md`](docs/PRODUCTION_DEPLOY.md) + [`docs/PRODUCTION_CHECKLIST.md`](docs/PRODUCTION_CHECKLIST.md) — SQL `003`–`029`, mint `fjsvc_`, Fly backend/engine + Vercel frontend. Partners integrate via YAML workflows and tenant-bound service tokens.

## Cursor Cloud specific instructions

The startup update script runs `uv sync --project backend` (also builds the Rust
engine via maturin/PyO3) and `npm install --prefix frontend`. Toolchain (`uv`,
Python 3.14, Rust 1.97 via `rust-toolchain.toml`, Node via nvm, native Postgres +
Redis) is baked into the VM image. First-run guide: [`docs/START_HERE.md`](docs/START_HERE.md)
(`npm run bootstrap -- --skip-docker` when using native Postgres/Redis). Notes
below are only the non-obvious caveats.

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

- Root DX: `npm run doctor` · `npm run quality` · `npm run dev:api` · `npm run dev:web` ([`docs/DEV.md`](docs/DEV.md))
- API: `cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --reload-dir app`
- Web: `cd frontend && npm start` (http://127.0.0.1:4200 — static landing; docs links only)
- Ops probes: `GET /health`, `GET /ready`, `GET /api/v1/capabilities`. Partner
  traffic uses sealed ingest + tenant service tokens — not a browser console.
  Backend pins Python 3.12 (`requires-python <3.14`), so `uv run` selects the
  supported interpreter instead of the system CPython 3.14.

### Frontend install scripts

`npm install` under npm 11 warns about ungated build scripts (esbuild/lmdb native
builds). The image ships a populated `frontend/node_modules`, so refresh installs
are fine; only a from-scratch `rm -rf node_modules` reinstall may need those build
scripts approved.

### Tests / lint / format / types

- First clone: `npm run bootstrap` (or `-- --skip-docker` on Cloud) · `npm run verify` after `dev:api`.
- Install hooks once: `npm run install-hooks` (pre-commit + commit-msg — [`docs/GIT.md`](docs/GIT.md)).
- Meta: `npm run quality` (fast) / `npm run quality:full` from repo root (`scripts/forjd_tooling.py`).
- Backend: `uv run ruff check .` / `uv run ruff format --check .`; tests: `uv run python -m unittest discover -s tests`.
- Engine: `cargo fmt --all -- --check`, `cargo clippy --no-default-features --features server,data-plane -- -D warnings`, `cargo test` (same flags as CI).
- Frontend: `npm run format:check`, `npm run typecheck`, `npm run test:all`; production build enforces `strictTemplates`. No ESLint — Prettier + TypeScript strict.
