# FORJD production cutover checklist

Safe sequence for taking FORJD as the exclusive sealed streaming engine for
partner subprocessors. FORJD stays **universal** — partner wire names belong
only in YAML `aliases` or in the partner’s own BFF rewrite.

Partner runbooks (example: DEML) live in the partner repo
(`docs/CUTOVER.md`, `docs/FORJD_PLATFORM_HANDOFF.md`). This file is the FORJD
platform side.

## Preflight

1. Apply SQL in order: `003` → `017` (`backend/sql/README.md`).
2. Confirm `POSTGRES_DSN` is Supabase (not Neon). Consolidation runbook:
   [`docs/NEON_TO_SUPABASE.md`](docs/NEON_TO_SUPABASE.md); verify with
   `backend/scripts/verify_supabase_post_migration.py`.
3. Confirm production forces RLS + crypto-session binding (`ENVIRONMENT=prod`).
4. Mint (or remint) tenant `fjsvc_` service accounts **after** `017` so scopes
   include sessions, replay/DLQ, status, and `analytics:read`.
5. Verify isolation gates:
   - `service_role` JWT rejected on application routes (including JWTs that also carry `app_metadata.forjd`)
   - cross-tenant `tenant_id` → `403`
   - sealed ingest stores ciphertext only (no plaintext columns)
   - `/api/v1/anomaly` returns `404` when `ENVIRONMENT=prod` (global PoC — use `/api/v1/ml/*`)
   - `ENGINE_API_TOKEN` set on Fly `forjd-engine` (process panics in prod if unset)
6. Deploy workflow YAML for the partner’s content types. Prefer canonical ids
   (`threat_telemetry` / `threat.*`). If the partner still sends legacy wire
   ids, copy `workflows/examples/partner_legacy_aliases.example.yaml` into an
   enabled partner-local overlay under `workflows/` — never hardcode product
   names in `app/` or `engine/`.
7. Staging smoke: register session → sealed ingest → projections list →
   replay/DLQ read (service token only).

## Deployment checklist (Fly + Vercel)

| Layer | Target | Action |
|-------|--------|--------|
| API | Fly `forjd-backend` | Deploy with `POSTGRES_DSN`, `REDIS_URL`, `SUPABASE_*`, `ENVIRONMENT=prod`, CORS including `https://forjd.co` and partner origins |
| Engine | Fly `forjd-engine` | `fly deploy` from `engine/`; set `ENGINE_URL` + `ENGINE_API_TOKEN` on API |
| Cache | Fly Dragonfly | Volume + `DFLY_requirepass`; API `REDIS_URL` |
| SQL | Supabase | Apply `003`–`017`; confirm `/ready` `schema_rls=true` |
| Web | Vercel `forjd.co` | `frontend/vercel.json`; `apiBaseUrl=https://backend.forjd.co` |
| UI kit | Vercel `ui.forjd.co` | Optional Storybook project |
| DNS | Vercel → Fly | Point `backend.forjd.co` A/AAAA at Fly as documented in root `README.md` |

## Cutover sequence (partner BFF)

| Phase | Partner action | FORJD expectation | Rollback |
|-------|----------------|-------------------|----------|
| **0 — Dual-write** | Partner may write sealed events to FORJD and keep a local metadata shadow for comparison. FORJD is source of truth for new sealed events. | Ingest + projections healthy | Partner stops FORJD writes |
| **1 — Read switch** | Partner reads projections / analytics / status from FORJD (service token). | Limit-based list APIs; no cursor claims | Partner flips read flag / empty fallback |
| **2 — Write switch** | Partner sealed path is FORJD-only (no legacy bus). | Same | Partner re-enables dual-write shadow only if needed |
| **3 — Decommission** | Partner removes local brokers/OLAP/workers; revokes unused creds. | Monitor DLQ / lag | Redeploy partner retired stack (costly) |

## Security confirmation

- E2EE: AES-256-GCM envelopes; AAD binds `tenant_id|client_event_id`; nonce
  uniqueness (`sql/013`); session revoke blocks ingest.
- Tenant isolation: RLS + `require_tenant_access` (human member **or** scoped
  `fjsvc_`); service tokens cannot create tenants or mint peers.
- Subprocessor model: partner end-user tokens (e.g. Firebase) never reach FORJD.
- JWKS algorithms allowlisted (`ES256`/`RS256`); service claims only from
  `app_metadata.forjd`.

## Rollback plan (FORJD side)

| Issue | Action |
|-------|--------|
| Bad deploy | Fly release rollback to previous image; keep SQL forward-only |
| Ingest errors | Check `/ready`, Dragonfly, crypto-session requirement, workflow YAML |
| Scope 403s | Remint `fjsvc_` after `017` (defaults do not rewrite existing rows) |
| Partner freeze | Partner sets write/read `off`; FORJD keeps stored ciphertext |

Do not soft-migrate schema in prod. Do not accept `service_role` JWTs.

## Post-cutover

- Monitor ingest 4xx/5xx, DLQ depth, projection lag, session register failures.
- Rotate `fjsvc_` on a schedule; partners store only secret references.
- Open ops ticket for tenant erase until an idempotent erase API ships.
- Engine: prefer `FORJD_ROLE=all` only after `./scripts/sync_engine_dataplane_secrets.sh`
  (DSNs + internode keys). Confirm `GET /ready` on `forjd-engine` includes
  `forjd_role=All`. Backend `/ready` exposes `engine` metadata (informational —
  Postgres/Redis/RLS still gate readiness).
- Rollback engine data plane without touching API: `fly secrets set FORJD_ROLE=engine -a forjd-engine`.

### Production readiness gates

| Gate | Command / check |
|------|-----------------|
| API | `curl -sS https://backend.forjd.co/ready` → `schema_rls` + postgres + redis (+ engine) |
| Engine | `curl -sS https://forjd-engine.fly.dev/ready` → `status=ready` |
| Sealed path | session register → sealed ingest → projections list (service token) |
| Partner BFF | DEML `FORJD_CUTOVER_PHASE=2` after dual-write shadow looks healthy |
| Anomaly PoC | `/api/v1/anomaly` → `404` in prod |
