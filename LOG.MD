# FORJD Development Log

## Log

- 2026-07-14: Initialized the backend project. Ran `mkdir backend && cd backend`, `uv init --app`, then added core dependencies: FastAPI + uvicorn[standard], pydantic-settings, python-dotenv, redis, asyncpg, httpx, Prefect[redis], and Pathway. This establishes the foundation for the API, workflow orchestration, and high-performance streaming.

- 2026-07-14: Created the basic application structure with `mkdir -p app/{core,api/v1,models,pipelines,services,utils}` and placeholder files. Added `.env.example` and ran initial `uv sync`. Tested with `uv run forjd`. Focused on keeping the setup lightweight and uv-driven.

- 2026-07-14: Added `.cursorrules`, `AGENTS.md`, and began this LOG.md to capture the full development journey for future writing and reflection.

- 2026-07-14: Scaffolded Angular frontend with `npx @angular/cli new frontend --standalone --routing --style=scss --skip-git`, then `ng add @angular/pwa`. Kept it lean (no Material) as the host app for a future forjd-ui library.

- 2026-07-14: Hardened backend Docker: multi-stage build (uv builder → slim runtime), `USER 1001`, pinned Prefect Compose image to `3.7.8-python3.12`. Added Angular CORS `:4200`, JSON stdout logging, soft Postgres/Redis clients in lifespan, `/ready` probe, and a minimal Prefect `forjd-hello` flow stub (call only when Prefect API is up).

- 2026-07-14: Generated `libs/forjd-ui` (`ng generate library`), added dark-first tokens + first `FjButton` primitive, replaced the CLI welcome page with a simple FORJD shell, and path-mapped `forjd-ui` to source for local iteration.

- 2026-07-14: Adopted the FJORD palette in forjd-ui tokens (Void Black / Operator Blue / Cold Steel / Muted Gold + status colors). Kept `--fj-*` names; `--fj-accent` aliases `--fj-primary`.

- 2026-07-14: Added Storybook 10.5 (`@storybook/angular-vite`) for forjd-ui with Button stories, plus Chromatic (`npm run chromatic`) for visual publishing. `.npmrc` uses `legacy-peer-deps` until Storybook peers catch TypeScript 6.

- 2026-07-14: Added Rollbar to the backend (`uv add rollbar`) with FastAPI `ReporterMiddleware`. Enabled only when `ROLLBAR_ACCESS_TOKEN` is set so local runs stay quiet.

- 2026-07-14: Added `@vercel/analytics` to the Angular app (`inject` in `main.ts`) and installed the Vercel agent plugin (`npx plugins add vercel/vercel-plugin`).

- 2026-07-14: Added `@vercel/speed-insights` alongside analytics in `main.ts`.

- 2026-07-14: Added Polars (`uv add polars`) for batch DataFrames; documented Pathway=streams vs Polars=batch in `.cursorrules` and `AGENTS.md`.

- 2026-07-14: Optimized agent docs — `AGENTS.md` is the short briefing/stack map; `.cursorrules` holds actionable constraints (secrets map, Pathway vs Polars, Storybook, rate-limit marked planned).

- 2026-07-15: Scaffolded Rust engine (`mkdir engine && cargo init --lib`). Added tokio, serde, tracing, Arrow/Parquet **55** for a future high-perf core (`cdylib`/`rlib`). Moved real code into `src/lib.rs` (Cargo’s crate root). Pinned Arrow at 55 instead of 52 — 52 fails to compile against current transitive chrono (`Datelike::quarter` clash).

- 2026-07-15: Added root `README.md` with prerequisites and step-by-step local run (env, Compose Dragonfly/Prefect, uv API + engine, Angular UI) plus Fly/Vercel deploy sketches.

- 2026-07-15: Wired an end-to-end **pulse PoC**: Angular UI → FastAPI → Rust `forjd-engine` (PyO3 + Arrow/Parquet), Polars, Pathway (soft-fail on CPython 3.14), Prefect, Supabase-ready Postgres, and Dragonfly. Added `POST/GET /api/v1/pulse`, `/api/v1/stack`, `sql/001_pulses.sql`, and Fly-ready `infra/dragonfly/`. Docker builds from repo root so the API image includes the engine wheel.

- 2026-07-16: Prepared the Rust engine for Fly.io: optional `server` feature with an axum HTTP binary (`/health`, `/ready`, `/v1/process`, `/v1/summarize`), multi-stage `engine/Dockerfile` (`USER 1001`, pinned `rust:1.97.0-bookworm`), and `engine/fly.toml`. Made PyO3 optional so the container builds without Python; maturin still uses `extension-module`.

- 2026-07-16: Hardened the pulse PoC around a modern Rust-first core: engine **0.2.0** (edition 2024, Arrow/Parquet **59**, PyO3 **0.29**) with real validation/enrichment, min/max summarize stats, `ENGINE_API_TOKEN` auth, body limits, timeouts, and security headers. Backend prefers `ENGINE_URL` HTTP (Compose `forjd-engine`) with PyO3 fallback; added optional `API_KEY`, security-header middleware, tighter CORS, Dragonfly `requirepass` locally, and private-only Fly Dragonfly TCP. Dropped unused Angular `zone.js` / deprecated animation packages; bumped Angular tooling to 22.0.7.

## Packages

Direct dependencies only. Star these on GitHub.

### Backend (Python)
- [fastapi](https://github.com/fastapi/fastapi) — API framework
- [uvicorn](https://github.com/Kludex/uvicorn) — ASGI server
- [pydantic-settings](https://github.com/pydantic/pydantic-settings) — settings from env
- [python-dotenv](https://github.com/theskumar/python-dotenv) — `.env` loading
- [redis-py](https://github.com/redis/redis-py) — Redis / Dragonfly client
- [asyncpg](https://github.com/MagicStack/asyncpg) — async Postgres (Supabase)
- [httpx](https://github.com/encode/httpx) — HTTP client (engine + probes)
- [Prefect](https://github.com/PrefectHQ/prefect) — workflow orchestration
- [Pathway](https://github.com/pathwaycom/pathway) — streaming / incremental processing
- [Polars](https://github.com/pola-rs/polars) — batch DataFrames
- [pyrollbar](https://github.com/rollbar/pyrollbar) — error reporting
- [uv](https://github.com/astral-sh/uv) — Python package manager
- [ruff](https://github.com/astral-sh/ruff) — linter / formatter (dev)
- [maturin](https://github.com/PyO3/maturin) — build Rust→Python extensions (dev / engine)

### Frontend (Angular / npm)
- [angular](https://github.com/angular/angular) — UI framework (+ CLI / build tooling)
- [rxjs](https://github.com/ReactiveX/rxjs) — reactive streams
- [tslib](https://github.com/microsoft/tslib) — TypeScript helpers
- [vercel/analytics](https://github.com/vercel/analytics) — web analytics
- [vercel/speed-insights](https://github.com/vercel/speed-insights) — performance insights
- [storybook](https://github.com/storybookjs/storybook) — component workshop
- [chromatic-cli](https://github.com/chromaui/chromatic-cli) — visual regression publishing
- [vite](https://github.com/vitejs/vite) — bundler (Storybook / Vitest)
- [vitest](https://github.com/vitest-dev/vitest) — unit tests
- [analog](https://github.com/analogjs/analog) — Vite plugin for Angular
- [ng-packagr](https://github.com/ng-packagr/ng-packagr) — library packaging
- [prettier](https://github.com/prettier/prettier) — code formatting
- [jsdom](https://github.com/jsdom/jsdom) — DOM for tests

### Engine (Rust)
- [tokio](https://github.com/tokio-rs/tokio) — async runtime
- [serde](https://github.com/serde-rs/serde) — serialization
- [serde_json](https://github.com/serde-rs/json) — JSON values
- [tracing](https://github.com/tokio-rs/tracing) — structured logging (+ subscriber)
- [arrow-rs](https://github.com/apache/arrow-rs) — Arrow + Parquet columnar I/O
- [bytes](https://github.com/tokio-rs/bytes) — byte buffers (Parquet reader)
- [thiserror](https://github.com/dtolnay/thiserror) — typed engine errors
- [subtle](https://github.com/dalek-cryptography/subtle) — constant-time token compare
- [PyO3](https://github.com/PyO3/pyo3) — Rust↔Python bindings (`forjd_engine`)
- [axum](https://github.com/tokio-rs/axum) — HTTP service for Fly.io (`server` feature)
- [tower](https://github.com/tower-rs/tower) — timeout / service stack (`server` feature)
- [tower-http](https://github.com/tower-rs/tower-http) — tracing, body limit, headers, request IDs

### Infra (runtime, not language crates)
- [Dragonfly](https://github.com/dragonflydb/dragonfly) — Redis-compatible cache (Fly.io: `infra/dragonfly/`)
- [PostgreSQL](https://github.com/postgres/postgres) — primary database (hosted on Supabase)
- [Supabase](https://github.com/supabase/supabase) — hosted Postgres for FORJD
- [Fly.io](https://github.com/superfly/fly) — Dragonfly + engine deployment target
