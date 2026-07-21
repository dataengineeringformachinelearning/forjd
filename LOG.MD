# FORJD Development Log

## Log

- 2026-07-20: Added supervised `ml-training` worker (daily SLA/threat/temporal retrains per active tenant + config-gated Hugging Face publishing under hashed tenant paths) and `retention` worker (bounded deletes for aged telemetry/results, expired crypto sessions, completed ingest receipts). Replaces the retired DEML-local daily training loop; `huggingface_hub` added to the ml group.
- 2026-07-20: Deployed partner provision end-to-end — applied `sql/026` on Fly, shipped `forjd-backend` + `deml-backend`; smoke confirmed idempotent `POST /api/v1/partner/provision`, DEML sealed per-account mapping for demo, and analytics overview 200 for both Joe (env token) and demo (sealed).
- 2026-07-19: Added partner provision API (`POST /api/v1/partner/provision` + `sql/026`) so DEML can auto-mint per-account FORJD tenants with `FORJD_PROVISION_TOKEN` — end users never hold `fjsvc_` tokens.
- 2026-07-19: Analytics overview now returns 24h rollup series
 (`time_series`, `uptime_series`, `threat_series`, `threat_severity`, `unique_visitors`, spiking forecast) so partner dashboards can chart latency/uptime/threats instead of scalars-only.
- 2026-07-19: Fixed empty landing CTAs — `FjButton` projected labels via a single `ng-template` + `NgTemplateOutlet` so href anchors show “API docs” / “ReDoc” (Angular drops `<ng-content>` inside `@if`/`@else` branches).
- 2026-07-19: Borrowed OpenBB’s Fetcher TET pattern (not the OpenBB package) for OSINT scanners — `app/services/fetchers/` with typed `FetchResult` envelope; crt.sh + HIBP migrated behind query→extract→transform while keeping existing HTTP façades. Addons stay the lean-core extension surface.
- 2026-07-19: Regression pass — backend 270 tests OK, engine `server,data-plane` 24 tests OK, frontend unit tests OK; live `/ready` green (postgres/redis/workers/engine). Pending deploy still required for Swagger-at-root and public status `tenant_id` omission.
- 2026-07-19: Landing polish — API root (`/` and `/docs`) serves FJORD-themed Swagger UI; Angular product landing uses forjd-ui `FjButton` (href) + `FjPanel` (card) primitives; removed the separate backend HTML marketing card.
- 2026-07-19: Security hardening follow-up — domain HIBP/SLA/discovered-endpoints use `require_tenant_access` (service principals + scopes); HIBP persists SHA-256 email digests only; public status slug DTO omits `tenant_id`; anonymous IP rate limits on public status/capabilities/addons/honeypot-hit routes plus auth-failure bucket; honeypot hit always returns `{ok: true}` (no 404 enumeration); tenant erase covers `correlation_receipts` and `threat_reports`; staging/stage get the same fail-closed schema defaults as production.
- 2026-07-19: Cleanup/optimization pass — aligned AGENTS/ARCHITECTURE/.cursorrules/READMEs with headless partner product (no console; rate limiting implemented; SQL through `025`); archived unused `sql/001`–`002` under `sql/historical/`; dropped unused `@angular/forms`; softened optional-ML “PoC” framing.
- 2026-07-19: Removed the pulse/stack/anomaly PoC layer and the runnable `/console` UI. Frontend and backend landings are static product pages (docs links only); deleted pulse/stack/anomaly APIs, unused batch helpers, browser seal/Supabase console clients, and `@supabase/supabase-js`. Product path remains sealed ingest + YAML workflows via authenticated APIs.
- 2026-07-19: Removed service-account remint scope drift by adding an API `include_tenant_erase` flag over canonical defaults; remint now excludes erase by default, safely encodes its request, and runbooks reflect current `003`–`025` migrations and `ml:read` defaults.
- 2026-07-19: Final polish pass — advertised `report_documents` in the public `/api/v1/capabilities` headless contract, added HTTP-level end-to-end tests for the reports lane (routing → auth → validation → SQL shape, PII rejection before DB), and cleared residual format drift. Gates green: full backend suite, engine 24 tests, frontend prod build + 4 UI tests.
- 2026-07-19: Added tenant-scoped report documents for partner user reports (DEML issue reports off Firebase) — `sql/022` (`report_documents` + RLS + `reports:read`/`reports:write` default scopes), strict pydantic contract reusing the SIEM PII-minimized metadata validator, `POST/GET /api/v1/reports/documents`, tenant-erase coverage, and 9 new tests. 164 backend tests green; remint partner tokens after applying `022`.
- 2026-07-19: Themed the interactive API docs — disabled stock Swagger UI and serve a FJORD dark-palette `GET /docs` (`app/core/docs_page.py`, swagger-ui-dist v5 with `--fj-*` color overrides + FORJD topbar). Frontend landing gained a six-tile capability grid; build, 4 UI tests, and 99 backend tests green.
- 2026-07-19: Replaced the frontend pulse/secure-stream PoC with a simple static landing page (brand, headline, doc links) mirroring the backend `GET /` landing. Deleted `pulse-api`/`secure-api`/`supabase`/`crypto` PoC modules, dropped `@supabase/supabase-js`, and removed unused HttpClient/Supabase env config. Build + 3 app tests green.
- 2026-07-19: Standardized the updated FORJD social/logo/favicon set across the frontend and API, removed superseded icon variants, and added complete canonical, Open Graph, Twitter, structured-data, manifest, robots, and sitemap coverage. Frontend production build and all 99 backend tests pass.
- 2026-07-19: Completed the optional add-on system with env-over-YAML enablement, default-off and DEML-all profiles, isolated Prefect ingest lifecycle hooks, contributor docs, and focused coverage. Backend verification passes 99 tests (3 skipped), with add-on lint and format checks clean.
- 2026-07-19: Add-on framework + Sentry + API landing. Added `app/addons/` registry (11 config-gated integrations, disabled by default; `FORJD_ADDONS=all` for partners) with `GET /api/v1/addons` and gated clients for OSV.dev, HoneyDB, go-cve-dictionary, nuclei, osv-scanner. Added optional Sentry (`uv sync --group sentry`, `SENTRY_DSN`) alongside Rollbar. Added a FJORD-styled `GET /` landing linking to Swagger `/docs`; frontend hero now links to the API docs. Backend gates green (93 tests).
- 2026-07-19: Final open-source quality pass — fixed 9 ruff violations + 35-file format drift, 3 clippy warnings (`let`-chains, `is_empty`), and switched all `torch.load` calls to `weights_only=True` (no-pickle rule). Scrubbed remaining partner naming (PDF report tokens rebranded FJORD `--fj-*`, deploy docs, test assertion, LOG), removed dead `parse_user_agent` module, extended AUTH scope docs and SQL README to the `003`–`019` path, raised the frontend initial-bundle budget to its real 516 kB footprint. All gates green: backend 84 tests, engine 22 tests + fmt + clippy, frontend 6 tests + prod build.
- 2026-07-18: Engine test fix — `validates_batch_contract` now asserts ciphertext-only ingest shape; `cargo test --features server,data-plane` green (22). Prefer that over `--all-features` locally (PyO3 link needs maturin/Python).
- 2026-07-18: Production verification — redeployed `forjd-backend` (exports/vulns service auth), applied SQL `017`–`019` (dropped crypto_sessions→auth.users FK), expanded the partner service account scopes; E2EE session→ingest→projections smoke passed (`scripts/e2e_sealed_ingest_smoke.py`).
- 2026-07-18: Dead-code cleanup — dropped unused `pathway_sealed_rollup` and `rust_sealed_metadata` alias, unused IP enrichment helpers, and `MIGRATE_MODE` partner back-compat; wiped local ETL `.run/` secrets.
- 2026-07-18: Code polish pass — removed anti-legacy framing from engine/bus/vulnerability comments, remint default names, and partner alias examples (`partner_aliases.example.yaml`); kept SQL filenames stable.
- 2026-07-18: Final documentation cleanup — presented FORJD as the universal secure streaming engine (no migration/lineage framing). Replaced cutover checklists with `docs/PRODUCTION_CHECKLIST.md`; removed `CUTOVER.md` / `CLEANUP_2026-07-18.md`; refreshed `AGENTS.md`, `ARCHITECTURE.md`, and README deploy links.
- 2026-07-18: Added production Neon→Supabase controlled ETL (`scripts/neon_supabase_etl/`) — YAML mappings/transforms, pgvector-aware schema, PK upserts, resumable watermarks, full/incremental modes, verify CLI; docs in `docs/NEON_TO_SUPABASE_ETL.md`. Optional `uv sync --group etl` (psycopg).
- 2026-07-18: Production deploy runbook — `docs/PRODUCTION_DEPLOY.md` + `docs/PRODUCTION_CHECKLIST.md` (live health/ready/engine All verified). Remaining: apply `sql/019`, redeploy security/perf to Fly, partner remint if erase needed.
- 2026-07-18: Security/perf pass — sticky session revoke; batch crypto-session checks; tenant-bound cursors; auth hot path skips DDL + debounces `last_used_at`; shared engine HTTP clients; `tenants:erase` opt-in (`sql/019`); rate-limited auth-failure logs; larger DB pool. Tests in `test_security_perf_pass.py`.
- 2026-07-18: Final cleanup pass — FORJD checklist is platform-only; Neon migrate/verify scripts generalized (`partner` + `TARGET_SCHEMA` / `PARTNER_CONTROL_SCHEMA`); removed hardcoded partner schema probes.
- 2026-07-18: Status CRUD for partners — PATCH/DELETE pages, list/update/delete services & incidents with `status:*` scopes; `apply_sql_migrations.py` now includes sql/018.
- 2026-07-18: Final partner cutover — `sql/018` default scopes (exports/vulns/integrations/`tenants:erase`), remint script, durable `POST /api/v1/tenants/{id}/erase`, and `docs/PRODUCTION_CUTOVER_CHECKLIST.md`. Existing `fjsvc_` tokens must be reminted after 017/018.
- 2026-07-18: Documented Neon→Supabase consolidation — FORJD Fly already on Supabase PG17+vector; Neon holds the partner control plane (PG18). Added `docs/NEON_TO_SUPABASE.md`, `scripts/pg_migrate_neon_to_supabase.sh`, and `backend/scripts/verify_supabase_post_migration.py` (RLS/vector/Realtime gates + rollback).
- 2026-07-18: Fixed FORJD_ROLE=all crash loop — minted FORJD_INTERNODE_* via sync_engine_dataplane_secrets.sh, redeployed engine (`forjd_role=All`, health passing). Backend `/ready` reports engine metadata without failing closed on engine blips; docs/ARCHITECTURE updated for post-cutover roles.
- 2026-07-18: Final validation hardenings — reject `service_role` before forjd claim shaping; gate global `/api/v1/anomaly` in production; require `ENGINE_API_TOKEN` on Fly/prod engine startup.
- 2026-07-18: Cutover prep complete across FORJD + partner — partner BFF dual-write/dual-read flags, Railway/Vercel checklists, and rollback live in the cutover runbooks in each repo; Angular wire contracts unchanged.
- 2026-07-18: Expanded CUTOVER.md with Fly/Vercel deployment checklist and FORJD-side rollback; partner dual-write/read remains BFF-owned so the platform stays universal.
- 2026-07-18: Hardened E2EE/auth boundaries — JWKS alg allowlist (no header trust), `app_metadata`-only service claims, CORS DELETE for revoke, auth-gated anomaly/compliance, production pulse write gate, routing-tag metadata values, byte-accurate `cipher_len`, YAML `content_types` aliases with prod fail-closed collisions.
- 2026-07-18: Removed the first-party partner telemetry YAML; partners map legacy wire ids via YAML aliases or BFF rewrite onto `threat_telemetry`. Resolved AUTH/test merge conflicts for universal alias wording.
- 2026-07-18: Finished partner↔FORJD cutover ops — Railway user-plane only (backend/frontend/dragonfly); retired data-plane services deleted; volumes queued for purge. Platform account mapped to FORJD tenant; service token projections verified. Engine left on `FORJD_ROLE=engine` after `all` crash-looped (DB/Redis secrets present; sealed process path healthy).
- 2026-07-17: Applied production SQL `003`–`016` on Supabase via forjd-backend (`SCHEMA_OK`); `/ready` now reports `schema_rls=true`. Partner Railway backend stripped legacy data-plane env; still needs `FORJD_SERVICE_TOKEN` + `FORJD_TENANT_ID` before cutover.
- 2026-07-17: Cutover prep for the partner subprocessor — added a partner telemetry workflow YAML (partner wire event types), engine secret sync script, and redeployed forjd-engine with current fly.toml (process-only until DB/Redis secrets are copied).
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
- [huggingface_hub](https://github.com/huggingface/huggingface_hub) — scheduled model artifact publishing (ml group)
- [uvicorn](https://github.com/Kludex/uvicorn) — ASGI server
- [pydantic-settings](https://github.com/pydantic/pydantic-settings) — settings from env
- [python-dotenv](https://github.com/theskumar/python-dotenv) — `.env` loading
- [redis-py](https://github.com/redis/redis-py) — Redis / Dragonfly client
- [asyncpg](https://github.com/MagicStack/asyncpg) — async Postgres (Supabase)
- [psycopg](https://github.com/psycopg/psycopg) — sync Postgres for Neon→Supabase ETL (`uv sync --group etl`)
- [httpx](https://github.com/encode/httpx) — HTTP client (engine + probes)
- [Prefect](https://github.com/PrefectHQ/prefect) — workflow orchestration
- [Pathway](https://github.com/pathwaycom/pathway) — streaming / incremental processing
- [Polars](https://github.com/pola-rs/polars) — batch DataFrames
- [pyrollbar](https://github.com/rollbar/pyrollbar) — error reporting
- [sentry-sdk](https://github.com/getsentry/sentry-python) — optional error tracking (`uv sync --group sentry`, `SENTRY_DSN`)
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

### Add-ons (optional integrations — disabled by default; `FORJD_ADDONS`)
- [osv.dev](https://github.com/google/osv.dev) — vulnerability advisories API (`osv-dev`)
- [osv-scanner](https://github.com/google/osv-scanner) — lockfile/SBOM vuln scanner (`osv-scanner`)
- [osv-scalibr](https://github.com/google/osv-scalibr) — SBOM / inventory extraction (`osv-scalibr`)
- [nuclei](https://github.com/projectdiscovery/nuclei) — template-based scanner (`nuclei`)
- [honeydb-python](https://github.com/honeydbio/honeydb-python) — honeypot threat intel (`honeydb`)
- [go-cve-dictionary](https://github.com/vulsio/go-cve-dictionary) — local CVE mirror (`go-cve-dictionary`)
- [jax](https://github.com/jax-ml/jax) — accelerated ML detectors, install on demand (`jax`)
- [acme](https://github.com/google-deepmind/acme) — RL research framework, descriptor only (`acme`)
- [robotframework](https://github.com/robotframework/robotframework) — acceptance-test automation (`robotframework`)
- [oss-fuzz](https://github.com/ShielderSec/oss-fuzz) — continuous fuzzing, CI/infra reference (`oss-fuzz`)
- [design-patterns-python](https://github.com/RefactoringGuru/design-patterns-python) — reference material (`design-patterns-python`)

### Frontend (Angular / npm)
- [angular](https://github.com/angular/angular) — UI framework (+ CLI / build tooling; includes `@angular/animations` for Storybook Vite)
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

## 2026-07-19 — Headless SIEM/SOAR security foundation

- Added sql/020 and `/api/v1/siem/signals`: strict, tenant-idempotent,
  PII-minimized normalized signals kept separate from sealed evidence, with
  bounded observables/metadata, search filters, correlation, cases, RLS, and
  metadata-only mutation audit events.
- Added scoped service-principal access for SIEM, cases, playbooks, tenant
  threat-intel reads, and opt-in threat-intel/ML writes; completed case,
  vulnerability, and versioned playbook PATCH surfaces.
- Replaced fake deferred SOAR success with durable idempotent playbook runs and
  per-action results. Webhooks require a real 2xx; partner-owned actions persist
  as `awaiting_ack` until explicitly acknowledged.
- Closed threat-intel tenant authorization gaps. Platform refresh/global TAXII
  now require an admin-claimed human; tenant TAXII requires its bound tenant and
  explicit scope. Custom TAXII/webhook egress is production HTTPS-only,
  allowlisted (`OUTBOUND_HOST_ALLOWLIST`), redirect-free, timeout/size bounded,
  and rejects non-public destinations.
- Added focused security tests covering scopes, tenant isolation, idempotency,
  strict signal validation, ownership-filtered updates, SSRF variants,
  redirects/oversize responses, and truthful durable run states.
- Added SaaS-grade SOAR retry delivery: immutable ordered run plans, stable
  webhook idempotency keys, bounded exponential/`Retry-After` scheduling,
  leased `SKIP LOCKED` worker claims, expired-lease recovery, and an explicit
  tenant-scoped operator retry endpoint. Permanent `4xx` and control-plane
  `awaiting_ack` actions never auto-retry.
- Made ACK decisions conditional and exact-replay idempotent, added whole-operation
  correlation receipts, routed the legacy alert bridge through normalized SIEM
  idempotency, and made privileged audit writes fail closed with database-enforced
  append-only audit rows.

## 2026-07-19 — Ingest, projection, replay, and tenant-lifecycle reliability

- Added sql/021 with canonical decoded ciphertext byte counts, immutable ingest
  fingerprints, deterministic projection/DLQ identities, retry lease/backoff
  state, and durable tenant-erasure receipts.
- Made sealed batch acceptance transactional. Exact duplicates are returned but
  not reprocessed; routing/encryption drift conflicts; processing failures return
  `ok=false` and enqueue every newly accepted event for replay.
- Replaced projection delete/insert writes with atomic versioned UPSERTs that
  preserve multiple detectors, use deterministic aggregate keys, and advance a
  monotonic `(created_at,event_id)` checkpoint under advisory leases.
- Keyset-paginated the projection worker across all tenants; replay now measures
  the same canonical byte count as live ingest, groups mixed workflows, and
  retries the exact tenant/event using exclusive leases and bounded backoff.
- Made tenant erase atomic and retry-idempotent without swallowing SQL errors in
  an aborted transaction. A deleted opaque erase credential now leaves only a
  prefix/SHA-256 tombstone and can authenticate solely to replay its completed
  same-tenant erase receipt; it remains invalid on every other route.
- Serialized canonical API acceptance against the matching projector snapshot
  fence and stamps insert statement time, preventing a worker watermark from
  passing an older uncommitted API event. Migration application is fail-fast
  per file with checksums and a ledger; post-migration verification covers
  reliability state.
- Removed poison-event head-of-line blocking: a failed page is atomically moved
  into a per-event, projection-versioned DLQ while the live cursor advances;
  later pages proceed, successful live recovery closes only matching DLQ rows,
  and retry fails closed rather than silently running a different version.
- Added an ASGI-level 8 MiB canonical-ingest body cap (including chunked bodies),
  reduced batches to 25 events, returns `413` before JSON validation, and
  advertises both limits through the machine-readable capabilities endpoint.
- Closed the post-commit ingest processing window with sql/024: acceptance now
  atomically writes ordered ciphertext-free workflow receipts with complete
  configuration snapshots and version/hash integrity. Replica-safe
  `SKIP LOCKED` leases recover crashes/restarts, exact duplicate retries wake
  original pending/failed groups, status is tenant-authorized, and one failed
  receipt cannot block later receipts. The API remains synchronously attempted
  and deliberately does not advertise a general `202` async contract.
- Moved sealed-ingest compliance evidence into that same acceptance transaction:
  a required, tenant-scoped metadata-only `ingest.batch` audit row now commits
  with the event and receipt or rolls them all back, and tenant erase removes
  every processing batch whose tenant array contains the erased tenant.
- Added focused reliability regressions; final backend validation is recorded
  after the concurrent SIEM/SOAR worker changes settle.

## 2026-07-19 — Public landing plus restored secure console

> **Superseded:** the `/console` operational surface was removed. Product UI is
> the static landing only; partners integrate via `fjsvc_` APIs. Realtime
> publication remains for consumers/partners — not a FORJD browser console.
> See the later 2026-07-19 entry on removing the runnable `/console` UI.

- ~~Preserved the static product landing at `/` and restored the functional Angular
  operational surface as a lazy `/console` route~~ (console removed; landing only).
- Historical note: that short-lived console briefly restored auth/session/Realtime
  demo controls; those paths no longer ship.
- Landing/routing tests and static product pages remain the frontend surface.

## 2026-07-19 — Replay-safe SIEM/SOAR completion and webhook authenticity

- Added sql/025 completion snapshots for normalized signals and whole-operation
  correlations. Exact completed retries now return the prior public result and
  never evaluate a newer correlation rule or playbook definition; processing
  retries remain able to heal pre-completion crashes.
- Bound playbook idempotency to the original trigger inputs and resolve existing
  runs before consulting a mutable current playbook version or active flag.
  Control-plane action results now include only the allowlisted immutable
  configuration operators need, and the DEML adapter preserves that contract.
- Added env-backed HMAC-SHA256 webhook signing through opaque `secret_ref`
  identifiers. Missing refs reject playbook writes or fail stored deliveries
  without sending an unsigned request; key material is never persisted,
  returned, or logged.
- Made webhook result persistence and its required audit receipt one atomic SQL
  statement, changed retry delivery to claim one row immediately before each
  request, and added an indexed continuation reconciler for post-success and
  post-ACK crash windows across multiple API replicas.
- Extended the post-migration verifier and production docs through sql/025.
  Focused validation passed: 58 FORJD SIEM/SOAR/worker/capability tests, 11 DEML
  adapter tests, Python compilation, Ruff lint, and Ruff formatting.

- 2026-07-19: Tightened durable runtime integrity and readiness: SQL/024 now
  enforces singleton-tenant ingest receipts down to each event, long ingest work
  heartbeats a fenced lease, Prefect fallback is decided before business work,
  and readiness gates on migrated SIEM/export contracts plus successful worker
  ticks rather than task liveness alone.

- 2026-07-19: Fixed three production blockers found during DEML end-to-end analytics testing: export queries bound int for `::text` interval params (asyncpg DataError on every export), completed-job TTL had the same bug, and the Prefect soft-fail probe booted the ephemeral server (beartype crash) because `env_ignore_empty` hid the production `PREFECT_API_URL=''` — the gate now reads the raw env. Provisioned the Tigris `forjd-exports` bucket + `OBJECT_STORAGE_*` secrets on Fly; sealed ingest → stream_results → export download now verified live.
- 2026-07-20: Added the supervised `analytics-rollup` worker (config-gated via `ANALYTICS_ROLLUP_INTERVAL_SECONDS`, readiness-gated in `/ready`): each tick upserts current+previous hour `aggregated_analytics` buckets for tenants with fresh `stream_results` and refreshes tenant `classical_anomaly` `ml_scores` (throttled by `ANALYTICS_ML_REFRESH_SECONDS`). This replicates the old DEML aggregation loop inside FORJD — sealed telemetry now flows to overview/CES/threat-report without any manual aggregate or /ml call. Added `scripts/smoke_sealed_ingest.py` (session registration + sealed events) and verified live on Fly: 12 events → projections → rollups (total_requests=24) → ml_scores populated.
- 2026-07-20: Doc-drift fix — bumped the production migration range from `003`–`025` to `003`–`026` (partner provision ledger) across `backend/sql/README.md`, `docs/PRODUCTION_DEPLOY.md`, `docs/PRODUCTION_CHECKLIST.md`, `AGENTS.md`, and `.cursorrules`; feature-specific `sql/025` citations left as-is.
