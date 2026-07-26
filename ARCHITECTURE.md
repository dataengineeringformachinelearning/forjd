# FORJD Architecture

Universal secure streaming engine. Stability and E2EE over novelty.

Scale guidance (leases, worker roles, what not to build): [`docs/SCALE.md`](docs/SCALE.md).

Non-obvious decisions (ADRs): [`docs/adr/`](docs/adr/README.md).

## Suite UI (chrome)

Visual identity is **suite-locked** with DEML Viking-UI: void-black surfaces, electric command `#2176ff`, institutional gold. FORJD `forjd-ui` is a thin `--fj-*` adapter — not a second design system. Contract: [`docs/SUITE_UI_UNIFICATION.md`](docs/SUITE_UI_UNIFICATION.md). Hosts: forjd.co and backend.forjd.co must match deml.app / marketing chrome (Storybook is local/Chromatic only).

Connection map (probes, auth lanes, Fly admission): [`docs/CONNECTION_MAP.md`](docs/CONNECTION_MAP.md).

Observability (logs, correlation, Rollbar/Sentry, never-log list): [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md).

Configuration inventory (env vars, feature flags, layers): [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) · [`config/forjd.catalog.yaml`](config/forjd.catalog.yaml).

Landing offline is graceful shell-only (not an offline data plane): [`docs/adr/0009-graceful-offline-landing.md`](docs/adr/0009-graceful-offline-landing.md).

Frontend state stays flat (scalars + derived computeds; index windows, not nested VMs): [`docs/adr/0010-normalize-flat-reactive-state.md`](docs/adr/0010-normalize-flat-reactive-state.md).

Client fetches share loading / error / success phases via `createFetchHandle`: [`docs/adr/0011-consistent-fetch-states.md`](docs/adr/0011-consistent-fetch-states.md).

Client caches use per-resource SWR (`createSwrCache`) with hard/soft invalidation and background revalidation: [`docs/adr/0012-swr-cache-invalidation.md`](docs/adr/0012-swr-cache-invalidation.md).

Browser XSS / open-redirect hygiene (`safeHref`, CSP `frame-ancestors 'none'`): [`docs/adr/0013-client-side-attack-hardening.md`](docs/adr/0013-client-side-attack-hardening.md). CSRF remains header-auth (`AUTH.md`).

UGC / third-party sanitization (`sanitize_text`, fetcher bounds, Sentry scrub): [`docs/adr/0014-sanitize-ugc-and-third-party.md`](docs/adr/0014-sanitize-ugc-and-third-party.md).

Sole rate limiter + input validation + context output encoding: [`docs/adr/0015-rate-limit-validation-output-encoding.md`](docs/adr/0015-rate-limit-validation-output-encoding.md).

Secure defaults (no session cookies, header parity, `credentials: 'omit'`, prod CORS/HTTPS): [`docs/adr/0016-secure-defaults-cookies-headers-api.md`](docs/adr/0016-secure-defaults-cookies-headers-api.md).

Secrets / sensitive data scrubbing (logs + Sentry/Rollbar + browser console): [`docs/adr/0017-secrets-and-sensitive-data.md`](docs/adr/0017-secrets-and-sensitive-data.md).

Defensive outbound HTTP (timeouts, no redirects, byte caps, JSON shape guards): [`docs/adr/0018-defensive-outbound-http.md`](docs/adr/0018-defensive-outbound-http.md).

## Principles

1. **Supabase-first** — Postgres + pgvector + Auth + Realtime for platform identity and durable storage.
2. **One durable ingest authority** — FastAPI owns authenticated sealed-event acceptance and its processing ledger; Rust owns the sealed-metadata hot path, outbox/relay, probes, and scheduling.
3. **Two explicit security lanes** — sealed evidence stays ciphertext-blind; a
   separate strict, selectively disclosed signal lane stores only normalized,
   PII-minimized fields needed for SIEM correlation and SOAR.
4. **Config over forks** — YAML/JSON workflows under `backend/workflows/` select processors, detectors, and projections per use case. Validate with `npm run validate:workflows` before deploy ([`docs/EXTENDING.md`](docs/EXTENDING.md), ADR-0028). No partner workflow write API.

## Layers

```
Static landing (forjd.co)   Docs / product surface only (no browser seal console)
Partner SaaS (subprocessor)  Tenant-scoped service token (fjsvc_… / M2M JWT)
Enterprise operators         Supabase Auth user JWT (API / admin paths)
        │
        ▼
FastAPI (forjd-backend)     Principal verify (user vs service), tenancy, Prefect
        │                    ├─ sealed evidence → telemetry_events (ciphertext)
        │                    └─ normalized signal → security_signals (no raw payload)
        ▼
forjd-engine (Rust)         /v1/sealed/pipeline · data-plane FORJD_ROLE
        │
        ▼
Supabase Postgres           telemetry_events (ciphertext) · stream_results
Dragonfly                   Streams bus · rate limits · cache
```

| Concern | Owner |
|---------|--------|
| Auth / principals | Supabase Auth users + `service_accounts` (sql/014); see `backend/docs/AUTH.md` |
| Sealed ingest API | FastAPI `/api/v1/ingest/events:batch` → Postgres (ciphertext-only); canonical partner/DEML contract |
| Rust ingest edge (fail-closed) | `/api/v1/ingest` returns `410 Gone`; the guard exists so stale integrations receive a hard rejection rather than a silent loss — FastAPI `/api/v1/ingest/events:batch` is the sole active ingest path |
| Crypto sessions / replay / status / analytics | FastAPI + `require_tenant_access` (human member **or** scoped `fjsvc_`) |
| Daemon/partner ingest | FastAPI canonical sealed batch with scoped `fjsvc_` token; durable acceptance and processing receipts |
| Rollup + size/rate detectors | Rust `run_sealed_pipeline` (dependency-free Python fallback) |
| Outbox → Streams, probes, cron | Rust data plane |
| Normalized SIEM signals / cases | FastAPI + `security_signals` / `incident_cases`; strict tenant scopes |
| Durable SOAR | Versioned playbooks + idempotent runs/action receipts; control-plane actions await acknowledgement |
| Batch analytics / ML | Python (Polars / Prefect / optional torch) |
| Realtime (consumers) | Supabase Realtime publication on `stream_results` / `telemetry_events` metadata for partner/consumer clients — not a FORJD product console |

## E2EE invariants

- Envelope: `algo`, `key_id`, `nonce`, `ciphertext`, optional `ratchet_header`
- AAD binds `tenant_id|client_event_id` (client-side)
- Unique `(tenant_id, key_id, nonce)` — rejects GCM nonce reuse (`sql/013`)
- `crypto_sessions` stores **public** X25519 keys only; `revoked_at` blocks ingest
- Rust / Python processors never receive ciphertext fields
- Internode AES-GCM on Dragonfly Streams is **transport** crypto (server-held keys), not client E2EE
- `security_signals` never stores ciphertext, raw evidence, credentials, email
  addresses, or direct usernames; it contains explicitly disclosed normalized
  fields and bounded observables only.

## Headless SIEM/SOAR

`POST /api/v1/siem/signals` is the normalized, tenant-idempotent signal lane.
`client_signal_id` identifies retries; reuse with different normalized content
returns `409`. Signals can correlate into tenant cases and matching playbooks.
The raw evidence that produced a signal stays on the sealed ingest lane.

SOAR execution is durable in `playbook_runs` and
`playbook_action_results`. Webhooks can succeed only after a real 2xx response.
Each run freezes its ordered action plan; later playbook edits cannot add, drop,
or reorder work in an in-flight version. Retryable webhook failures (`408`,
`425`, `429`, `5xx`, and network errors) use bounded exponential backoff,
`Retry-After` capping, stable delivery idempotency keys, and leased
`SKIP LOCKED` worker claims. Permanent `4xx` failures require an explicit
operator retry. Control-plane actions are never auto-retried.
Partner-owned actions such as `block_ip` or `revoke_api_key` remain
`awaiting_ack` until the control plane acknowledges the action result. Custom
TAXII and webhook egress is HTTPS-only in production, has redirects disabled,
rejects non-public addresses, and must match `OUTBOUND_HOST_ALLOWLIST`.

Manual correlations have tenant/key/request-fingerprint receipts covering case
and playbook effects. Privileged SIEM/SOAR audit writes fail closed, and SQL
enforces `audit_events` as append-only.

## Configurable pipelines

```yaml
pipeline:
  processor: sealed_metadata
  steps: [rollup, size_anomaly, rate_anomaly]
```

Processors resolve via `app.workflows.processors.REGISTRY`. Detectors via
`app.workflows.detectors.REGISTRY`. Add a vertical by dropping YAML — do not fork ingest.
Start from `backend/workflows/examples/`; validate locally/CI; optional
`WORKFLOWS_STRICT=1` fails closed at registry load. Partner control planes (e.g.
DEML `/pipeline`) may compose/export YAML only — FORJD still owns deploy/reload.

Partner wire ids map through config only:

```yaml
aliases:
  workflow_ids: [partner_workflow_id]
  event_types:
    threat.metric: [partner.metric]
```

The registry maps aliases to the canonical workflow family before storage.
Product names never belong in engine/API code.

## Subprocessor model (partner SaaS)

- A trusted partner keeps **its own** end-user auth (e.g. Firebase).
- FORJD issues a **tenant-bound** service principal; that token is the only
  credential the subprocessor uses against FORJD.
- Service principals cannot cross tenants, create tenants, or mint other keys.
- Default scopes cover ingest, projections, crypto sessions, replay/DLQ,
  status management, analytics reads, normalized SIEM, cases, playbooks, and
  report documents (`reports:read`/`reports:write`, `sql/022`).
  Global feed administration, tenant TAXII writes, erase, and generic ML writes
  remain human-only or explicit opt-ins; DEML provisioning uses an explicit
  least-privilege profile with `ml:write` (see `AUTH.md`).
- Details, scopes, and minting API: [`backend/docs/AUTH.md`](backend/docs/AUTH.md).

## SQL apply order

`003` → `028` under `backend/sql/` (see that folder’s README). Production forces
`SOFT_MIGRATE_SCHEMA=false`, `REQUIRE_RLS=true`, `REQUIRE_CRYPTO_SESSION=true`.
Realtime + `projection_feed` land in `015`; ML scores/runs in `016`; service-principal
session actor + expanded default scopes in `017`; partner domain scopes + erase in `018`;
erase opt-in defaults in `019`; normalized SIEM/SOAR and scoped defaults in
`020`; sealed-ingest/projection/replay reliability state in `021`; report
documents in `022`; durable exports in `023`; durable ingest-processing
recovery in `024`; immutable SIEM/SOAR replay plus continuation recovery
in `025`; partner provision / service-principal cutover support
(`sql/026_partner_provisions.sql` plus partner-qualified isolation,
credential/tenant FK integrity, and the DEML scope upgrade in `027`); and status
page/service/probe tenant integrity plus per-service latest-probe indexing in `028`.

Postgres host is **Supabase** (`POSTGRES_DSN`). Partner control-plane databases may
optionally co-locate in the same project under a non-`public` schema — see
[`docs/NEON_TO_SUPABASE.md`](docs/NEON_TO_SUPABASE.md).

## Production deploy

Operator runbook: [`docs/PRODUCTION_DEPLOY.md`](docs/PRODUCTION_DEPLOY.md).
Checklist: [`docs/PRODUCTION_CHECKLIST.md`](docs/PRODUCTION_CHECKLIST.md).

### Engine roles

| `FORJD_ROLE` | What runs | Required secrets |
|--------------|-----------|------------------|
| `engine` (default) | Arrow/Parquet process HTTP only | `ENGINE_API_TOKEN` |
| `ingest` | **Retired** — sealed edge returns `410 Gone`; do not deploy as an active ingest path | (historical) |
| `relay` / `scheduler` / `normalizer` | Bus workers | + DSNs + **internode keys** |
| `all` | Relay + scheduler + probe + normalizer (canonical sealed ingest remains FastAPI) | DSNs + internode keys |

On Fly, bus roles default to `FORJD_INTERNODE_ENCRYPTION=required`. Set
`FORJD_INTERNODE_ACTIVE_KID` / `FORJD_INTERNODE_KEYS` with
[`scripts/sync_engine_dataplane_secrets.sh`](scripts/sync_engine_dataplane_secrets.sh).
Process-only mode: `fly secrets set FORJD_ROLE=engine -a forjd-engine`.
Role-aware `/ready` checks the dependencies each selected role needs. Probe/all
roles additionally require every configured status target to have a recently
persisted observation; target outages remain product state, while stale probe
progress makes the engine itself not ready.

End-to-end partner path: partner BFF → FORJD API (`fjsvc_`) →
Supabase Postgres (ciphertext + projections) → optional engine sealed pipeline
via `ENGINE_URL`.

### Partner BFF live lane (e.g. DEML)

Partner end users authenticate only to the partner control plane (Firebase at
DEML). The browser never holds `fjsvc_` tokens and never opens a Supabase
Realtime channel for product data. Supported live updates:

```
Browser (Firebase JWT) → partner BFF SSE (GET /api/v1/analytics/live)
                       → FORJD GET /api/v1/projections?tenant_id=&since=
                         (tenant-bound fjsvc_ on the BFF only)
```

SSE frames carry change ticks (`count` / `cursor`) only — never projection
payloads, ciphertext, or credentials. Dashboards then refresh via the
authenticated BFF read adapters.

## Explicit non-goals

- Accepting partner SaaS end-user tokens at the FORJD edge
- Browser-held `fjsvc_` tokens or direct browser→FORJD product data paths
- Server-side plaintext ML on sealed payloads
- Python reimplementation of Rust relay / probe / normalizer / scheduler
- Product-specific workflow or event names in `app/` / `engine/` (YAML only)
