# FORJD Development Log

## Log

- 2026-07-18: Final partner cutover — `sql/018` default scopes (exports/vulns/integrations/`tenants:erase`), remint script, durable `POST /api/v1/tenants/{id}/erase`, and `docs/PRODUCTION_CUTOVER_CHECKLIST.md`. Existing `fjsvc_` tokens must be reminted after 017/018.
- 2026-07-18: Documented Neon→Supabase consolidation — FORJD Fly already on Supabase PG17+vector; Neon holds DEML Django (PG18). Added `docs/NEON_TO_SUPABASE.md`, `scripts/pg_migrate_neon_to_supabase.sh`, and `backend/scripts/verify_supabase_post_migration.py` (RLS/vector/Realtime gates + rollback).
- 2026-07-18: Fixed FORJD_ROLE=all crash loop — minted FORJD_INTERNODE_* via sync_engine_dataplane_secrets.sh, redeployed engine (`forjd_role=All`, health passing). Backend `/ready` reports engine metadata without failing closed on engine blips; docs/ARCHITECTURE updated for post-cutover roles.
- 2026-07-18: Final validation hardenings — reject `service_role` before forjd claim shaping; gate global `/api/v1/anomaly` in production; require `ENGINE_API_TOKEN` on Fly/prod engine startup.
- 2026-07-18: Cutover prep complete across FORJD + DEML — partner BFF dual-write/dual-read flags, Railway/Vercel checklists, and rollback live in `CUTOVER.md` (FORJD) and DEML `docs/CUTOVER.md`; Angular wire contracts unchanged.
- 2026-07-18: Expanded CUTOVER.md with Fly/Vercel deployment checklist and FORJD-side rollback; partner dual-write/read remains BFF-owned so the platform stays universal.
- 2026-07-18: Hardened E2EE/auth boundaries — JWKS alg allowlist (no header trust), `app_metadata`-only service claims, CORS DELETE for revoke, auth-gated anomaly/compliance, production pulse write gate, routing-tag metadata values, byte-accurate `cipher_len`, YAML `content_types` aliases with prod fail-closed collisions.
- 2026-07-18: Removed first-party `deml_telemetry.yaml`; partners map legacy wire ids via YAML aliases or BFF rewrite onto `threat_telemetry`. Resolved AUTH/test merge conflicts for universal alias wording.
- 2026-07-18: Finished DEML↔FORJD cutover ops — Railway user-plane only (backend/frontend/dragonfly); retired data-plane services deleted; volumes queued for purge. Platform account mapped to FORJD tenant; service token projections verified. Engine left on `FORJD_ROLE=engine` after `all` crash-looped (DB/Redis secrets present; sealed process path healthy).
- 2026-07-17: Applied production SQL `003`–`016` on Supabase via forjd-backend (`SCHEMA_OK`); `/ready` now reports `schema_rls=true`. Railway deml-backend stripped legacy data-plane env; still needs `FORJD_SERVICE_TOKEN` + `FORJD_TENANT_ID` before cutover.
- 2026-07-17: Cutover prep for DEML subprocessor — added `deml_telemetry.yaml` (deml.metric/deml.alert), engine secret sync script, and redeployed forjd-engine with current fly.toml (process-only until DB/Redis secrets are copied).
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

- 2026-07-15: Fixed Fly Dragonfly deploy packaging — added `infra/dragonfly/Dockerfile` (official image pin) so GitHub/Fly builders stop failing with no build context; documented required `dragonfly_data` volume + dashboard path fields.

- 2026-07-15: Added root `README.md` with prerequisites and step-by-step local run (env, Compose Dragonfly/Prefect, uv API + engine, Angular UI) plus Fly/Vercel deploy sketches.

- 2026-07-15: Wired an end-to-end **pulse PoC**: Angular UI → FastAPI → Rust `forjd-engine` (PyO3 + Arrow/Parquet), Polars, Pathway (soft-fail on CPython 3.14), Prefect, Supabase-ready Postgres, and Dragonfly. Added `POST/GET /api/v1/pulse`, `/api/v1/stack`, `sql/001_pulses.sql`, and Fly-ready `infra/dragonfly/`. Docker builds from repo root so the API image includes the engine wheel.

- 2026-07-16: Prepared the Rust engine for Fly.io: optional `server` feature with an axum HTTP binary (`/health`, `/ready`, `/v1/process`, `/v1/summarize`), multi-stage `engine/Dockerfile` (`USER 1001`, pinned `rust:1.97.0-bookworm`), and `engine/fly.toml`. Made PyO3 optional so the container builds without Python; maturin still uses `extension-module`.

- 2026-07-16: Fixed Fly Dragonfly image pull — Docker Hub no longer carries current tags (`v1.39.0` 404); pointed `infra/dragonfly/Dockerfile` at `docker.dragonflydb.io/dragonflydb/dragonfly:v1.39.0` to match Compose. Volume `dragonfly_data` attached in `iad`; first deploy succeeded after the registry fix.

- 2026-07-16: Hardened the pulse PoC around a modern Rust-first core: engine **0.2.0** (edition 2024, Arrow/Parquet **59**, PyO3 **0.29**) with real validation/enrichment, min/max summarize stats, `ENGINE_API_TOKEN` auth, body limits, timeouts, and security headers. Backend prefers `ENGINE_URL` HTTP (Compose `forjd-engine`) with PyO3 fallback; added optional `API_KEY`, security-header middleware, tighter CORS, Dragonfly `requirepass` locally, and private-only Fly Dragonfly TCP. Dropped unused Angular `zone.js` / deprecated animation packages; bumped Angular tooling to 22.0.7.

- 2026-07-16: Deployed `forjd-engine` and `forjd-backend` to Fly (`fly.api.toml` at repo root; Dockerfile venv path fix so `python -m uvicorn` starts). Renamed the API app from `forjd-api` → `forjd-backend`. Health passes; Postgres/Dragonfly readiness still need DSN/6PN follow-up.

- 2026-07-16: Wired production domain [forjd.co](https://forjd.co): frontend `apiBaseUrl` → `https://backend.forjd.co`, Fly cert for `backend.forjd.co` on `forjd-backend`, CORS allows `https://forjd.co` (apex only).

- 2026-07-16: Kept Fly `forjd-backend` / `forjd-engine` always on (`auto_stop_machines=off`, `min_machines_running=1`) so idle stop + 6PN engine calls do not leave the stack suspended.

- 2026-07-16: Fixed Fly 6PN private links — engine HTTP now binds `[::]` (was IPv4-only `0.0.0.0`); backend Redis/httpx prefer IPv6 for `*.internal`; redeployed Dragonfly so `DFLY_bind=::` actually applied (machine had been stuck on the first IPv4-era deploy).

- 2026-07-16: Moved backend from CPython **3.14 → 3.12**, bumped Pathway **0.2.0 → 0.31.1**, and uv-override `beartype<0.16` (Pathway needs it; Prefect/pydocket wants ≥0.20 — override prefers Pathway). Pulse Pathway helper uses `table_from_pandas` / `table_to_pandas`.

- 2026-07-16: Enforced forjd-ui-first UI via a frontend Cursor rule, then moved existing app shell typography + panel/status-list patterns into the library (`FjPanel`, `FjStatusList`, `_typography.scss` + type tokens). Pulse page now consumes those primitives; page layout stays in the app.

- 2026-07-16: Added `frontend/ui` Vercel project root to host static forjd-ui Storybook at `ui.forjd.co` (build copies `dist/storybook/forjd-ui`). Chromatic remains for visual review; this is the public docs site.

- 2026-07-16: Split Vercel project builds — `forjd` → `npm run build` at forjd.co; `ui` → `npm run build-storybook` at ui.forjd.co (same `frontend/` root; build/output set per project so shared `vercel.json` only has rewrites/headers). Linked `ui` to the GitHub repo; added `@angular/animations` so Storybook’s Vite build succeeds on clean `npm ci`.

- 2026-07-16: Added unsupervised ML PoC — PyTorch LSTM-Autoencoder (optional `uv sync --group ml`) with reconstruction-error scoring, Prefect `forjd-anomaly`, and Supabase pgvector table `anomaly_embeddings` (`sql/002_anomaly_embeddings.sql`). Chose LSTM-AE over TFT because TFT is supervised forecasting; wired `POST /api/v1/anomaly/fit|score` + UI “Fit + score anomaly”.

- 2026-07-16: Wired Fly for the ML PoC — Dockerfile `uv sync --group ml` with pytorch-cpu index (dropped CUDA lock deps), entrypoint volume chown for `/data/models`, `ml_models` mount + 2GB VM in `fly.api.toml`. Removed unused Prefect `hello.py` stub and empty `app/utils`.

- 2026-07-16: Deployed `forjd-backend` with torch CPU + volume; fixed Prefect `HOME`/`PREFECT_HOME` after setpriv, renamed SQL column `window` → `series_window` (reserved keyword). Prod fit/score + pgvector persist verified on backend.forjd.co.

- 2026-07-16: Started Signal-inspired secure streaming path — `sql/003_secure_tenancy.sql` (tenants, RLS, E2EE `telemetry_events`, tenant `embedding_vectors`), Supabase JWT verify (JWKS/HS256), AES-256-GCM envelope helpers, `POST /api/v1/ingest/*` + tenants API, Prefect `forjd-ingest`. Server stores ciphertext only; ApiKey middleware no longer hijacks Bearer JWTs.

- 2026-07-16: Next secure-stream step — applied `003` + Realtime publication on Supabase; Angular WebCrypto seal helper + Supabase Auth/Realtime client; Pathway sealed-metadata rollup on ingest; Fly `SUPABASE_URL` secrets + backend redeploy. UI “Secure stream” panel needs public `supabaseAnonKey` in environments.

- 2026-07-16: Hardened E2EE foundation — X25519 ECDH + HKDF session keys in `app.core.crypto`, `sql/004_crypto_sessions.sql` (public-key directory + RLS), `POST/GET /api/v1/sessions`, Angular `crypto/x25519.ts`, and unittest coverage. Documented Double Ratchet / forward secrecy: server stores ciphertext + opaque headers only.

- 2026-07-16: Added Cursor rule `.cursor/rules/section-comments.mdc` (alwaysApply) for minimal scannable section comments; annotated the secure-path modules (auth, crypto, ingest, sessions, tenants, Pathway/Prefect, Angular crypto) so sections are readable from comments alone.

- 2026-07-16: Closed secure-stream gaps — canonical `POST /api/v1/ingest`, Prefect `forjd-ingest` runs Pathway transform + metadata anomaly (z-score / max cipher_len), persists `stream_results` (`sql/005`) under RLS, plus `GET /api/v1/ingest/results`. Server still never opens E2EE ciphertext.

- 2026-07-16: Universalized the streaming core for multi-SaaS use cases — YAML/JSON workflows under `backend/workflows/` with a processor registry (`app/workflows/`), generic ingest fields (`event_type`, `workflow_id`, `encryption`), `sql/006` (`use_cases`, `sealed_events` view), and `GET /api/v1/workflows`. Verticals are config files (e.g. `threat_telemetry.yaml`), not core forks. Added `pyyaml`.

- 2026-07-16: Added durable projections + checkpoints + DLQ (`sql/007`, `POST /api/v1/projections/run`, `POST /api/v1/replay`), status pages (`sql/008`, public slug read), and pluggable detectors (`size_anomaly` / `rate_anomaly` under `app/workflows/detectors/`). Prefect `forjd-project` soft-fails like ingest; E2EE path unchanged (metadata-only projectors).

- 2026-07-16: Second-pass hardening for universal secure streaming — neutral platform defaults (`application/forjd-event+v1`), bound `envelope.key_id` → `crypto_sessions` when `REQUIRE_CRYPTO_SESSION` (forced in production), metadata allowlist, fail-closed schema/RLS (`SOFT_MIGRATE_SCHEMA` / `REQUIRE_RLS`), YAML→`use_cases` sync on boot, live ingest advances projection watermarks + optional `PROJECTION_TICK_SECONDS` worker. Angular PoC registers X25519 session before seal/ingest.

- 2026-07-17: Built Rust data plane — Dragonfly Streams + Postgres `outbox_events` (`sql/009_daemon_data_plane.sql`) instead of Kafka/ClickHouse; folded into `forjd-engine` data-plane roles.

- 2026-07-17: Full modernization pass for universal secure SaaS — promoted `EventType` / `PipelineConfig` / `ProjectionDefinition` (extensible `pipeline.steps` + `detector_params`), extracted daemon CPE into an optional plugin module with config-driven `rate_limit_rpm`, added metadata-only `audit_events` (`sql/010`), fail-closed prod defaults (Fly-aware), shared Prefect soft-fail helper, and service-role projection ticks without synthetic AuthUser. Verticals remain YAML configs, not platform core.

- 2026-07-17: Merged `forjd-daemon` into `forjd-engine` — one crate/binary/Fly app (`src/data_plane/`, `--features server,data-plane`, `FORJD_ROLE`). Bumped Fly VM to shared-cpu-2x / 2GB; Compose wires Postgres/Dragonfly into the engine. CPE stays opt-in (`FORJD_ROLE=cpe`), not part of `all`.

- 2026-07-17: Added domain security layer — `sql/011_domain_security.sql` + APIs for threat intel (abuse.ch/TAXII), SOC cases, playbooks, Polars exports, and tenant-scoped ThreatModel train/score. Uses `tenant_id` + opaque `actor_id` (no end-user FK). Skipped reintroducing Rust-owned relay/probe/normalizer/scheduler loops.

- 2026-07-17: Expanded domain scanners wave 2 — Lighthouse, OSINT/HIBP/Ahmia, Firecrawl tech enrichment + SSRF URL guards, assets/vulns CRUD, vulnerability ledger, analytics rollups/CES, honeypots, PDF reports (+ optional S3), SOC compliance, SLA training, security-alert ingest. Added `sql/012_domain_scanners.sql`, optional `ml` sklearn + `storage` boto3 groups.

- 2026-07-17: Modernized FORJD as Supabase-first secure streaming — documented architecture (no ClickHouse/Firebase), Rust `pipeline` module + `/v1/sealed/pipeline` + PyO3 `run_sealed_pipeline` for ciphertext-blind rollup/detectors (Pathway fallback), E2EE hardening (`sql/013` nonce uniqueness + session revoke), daemon ingest rejects plaintext records, Supabase Edge Function `peer-sessions` stub.

- 2026-07-17: Added tenant-scoped service accounts for enterprise users + subprocessors — `sql/014`, `AuthUser.kind` user vs service, opaque `fjsvc_` tokens and Supabase M2M claim binding, `require_tenant_access` on ingest/projections, mint/revoke API, `backend/docs/AUTH.md`. FORJD only accepts tenant-bound service credentials, never partner end-user tokens.

- 2026-07-17: Tightened the universal secure streaming core — `sql/015` Realtime publication + `projection_feed` + cursor indexes, default service scopes include `sessions:*`, projections/results APIs accept `since`/`after_id` live cursors, example workflow `threat_telemetry.yaml`, and documented the subprocessor HTTP sequence in `AUTH.md` + ingest/projections comments.

- 2026-07-17: Trimmed pointer-only cruft for a leaner tree — removed `infra/engine/`, `engine/daemon/`, `frontend/ui/`, and unused `.example.env`; folded Storybook deploy notes into `frontend/README.md`.

- 2026-07-17: Scrubbed product-specific naming from docs, comments, SQL headers, PDF branding, and tests so FORJD reads as a standalone universal streaming platform; subprocessors are generic partner SaaS backends.

- 2026-07-17: Shipped unified ML catalog (`GET/POST /api/v1/ml/...`) — Isolation Forest + One-Class SVM, RF + HistGradientBoosting, Transformer sequence AE, TFT-lite + NeuralSeasonal + GRU/LSTM P99, EventEncoder embeddings, and NorseSSN spiking temporal forecaster (optional `norse` via `ml-spiking`; Sentence-Transformers via `ml-nlp`). Existing LSTM-AE + threat/SLA routes kept.

- 2026-07-17: Optimized ML for Supabase — `sql/016` (`ml_scores` + training_runs family + Realtime), hydrate fit/score from `stream_results` metadata (never ciphertext), persist runs/latents/scores under tenant RLS (`training_runs`, `embedding_vectors`, `ml_scores`), and `GET /api/v1/ml/scores` for polling/Realtime consumers.

- 2026-07-18: Unblocked partner cutover: YAML `aliases` map legacy workflow/event wire ids onto universal families (no product names in code); extended `fjsvc_` scopes to sessions, replay/DLQ, status, and analytics:read; sql/017 drops crypto_sessions→auth.users FK so service principals can register sessions.

- 2026-07-18: Final universality pass — removed first-party product aliases from `threat_telemetry.yaml`; added `workflows/examples/partner_legacy_aliases.example.yaml` (not registry-loaded); PDF author → FORJD; cutover checklist in root `CUTOVER.md`.

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
- [pytorch](https://github.com/pytorch/pytorch) — LSTM-AE / transformers / forecasting / NorseSSN fallback (`uv sync --group ml`)
- [numpy](https://github.com/numpy/numpy) — window tensors for ML (`ml` group)
- [scikit-learn](https://github.com/scikit-learn/scikit-learn) — Isolation Forest, OCSVM, RF, HistGradientBoosting (`ml` group)
- [norse](https://github.com/norse/norse) — optional LIF cells for NorseSSN (`uv sync --group ml-spiking`)
- [sentence-transformers](https://github.com/UKPLab/sentence-transformers) — optional event similarity (`uv sync --group ml-nlp`)
- [boto3](https://github.com/boto/boto3) — S3-compatible export/report storage (`uv sync --group storage`)
- [pyjwt](https://github.com/jpadilla/pyjwt) — Supabase Auth JWT verification
- [cryptography](https://github.com/pyca/cryptography) — AES-256-GCM E2EE envelopes
- [PyYAML](https://github.com/yaml/pyyaml) — workflow definition loading
- [uv](https://github.com/astral-sh/uv) — Python package manager
- [ruff](https://github.com/astral-sh/ruff) — linter / formatter (dev)
- [maturin](https://github.com/PyO3/maturin) — build Rust→Python extensions (dev / engine)

### Frontend (Angular / npm)
- [angular](https://github.com/angular/angular) — UI framework (+ CLI / build tooling; includes `@angular/animations` for Storybook Vite)
- [supabase-js](https://github.com/supabase/supabase-js) — Auth + Realtime client for sealed stream UI
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

### Engine (Rust — process + data plane)
- [tokio](https://github.com/tokio-rs/tokio) — async runtime
- [serde](https://github.com/serde-rs/serde) — serialization
- [serde_json](https://github.com/serde-rs/json) — JSON values
- [tracing](https://github.com/tokio-rs/tracing) — structured logging (+ subscriber)
- [arrow-rs](https://github.com/apache/arrow-rs) — Arrow + Parquet columnar I/O
- [bytes](https://github.com/tokio-rs/bytes) — byte buffers (Parquet reader)
- [thiserror](https://github.com/dtolnay/thiserror) — typed engine errors
- [subtle](https://github.com/dalek-cryptography/subtle) — constant-time token compare
- [PyO3](https://github.com/PyO3/pyo3) — Rust↔Python bindings (`forjd_engine`)
- [axum](https://github.com/tokio-rs/axum) — HTTP (`server` / `data-plane`)
- [tower](https://github.com/tower-rs/tower) — timeout / service stack
- [tower-http](https://github.com/tokio-rs/tower-http) — tracing, body limit, headers, request IDs
- [sqlx](https://github.com/launchbadge/sqlx) — Postgres outbox / scheduler / probes (`data-plane`)
- [redis-rs](https://github.com/redis-rs/redis-rs) — Dragonfly Streams bus + rate limits (`data-plane`)
- [reqwest](https://github.com/seanmonstar/reqwest) — health probes / OTLP (`data-plane`)
- [aes-gcm](https://github.com/RustCrypto/AEADs) — internode envelope encryption (`data-plane`)
- [anyhow](https://github.com/dtolnay/anyhow) — data-plane error context
- [uuid](https://github.com/uuid-rs/uuid) — lease / event ids
- [chrono](https://github.com/chronotope/chrono) — scheduler UTC buckets
- [futures](https://github.com/rust-lang/futures-rs) — bounded concurrency
- [sha2](https://github.com/RustCrypto/hashes) — ingest API key + custody hashes
- [opentelemetry-rust](https://github.com/open-telemetry/opentelemetry-rust) — optional OTLP tracing
- [rustls](https://github.com/rustls/rustls) — TLS for probes and Dragonfly

### Infra (runtime, not language crates)
- [Dragonfly](https://github.com/dragonflydb/dragonfly) — Redis-compatible cache (Fly.io: `infra/dragonfly/`)
- [PostgreSQL](https://github.com/postgres/postgres) — primary database (hosted on Supabase)
- [Supabase](https://github.com/supabase/supabase) — hosted Postgres for FORJD
- [pgvector](https://github.com/pgvector/pgvector) — vector extension for LSTM-AE latents (Supabase)
- [Fly.io](https://github.com/superfly/fly) — Dragonfly + engine deployment target
