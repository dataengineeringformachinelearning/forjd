# FORJD Architecture

Universal secure streaming engine. Stability and E2EE over novelty.

## Principles

1. **Supabase-first** — Postgres + pgvector + Auth + Realtime for platform identity and durable storage.
2. **Rust-max hot path** — ingestion edge, sealed-metadata pipeline, outbox/relay, probes, and scheduling live in `forjd-engine`.
3. **Ciphertext-blind server** — AES-256-GCM envelopes with X25519/HKDF session keys derived client-side; server stores ciphertext and opaque ratchet headers only.
4. **Config over forks** — YAML/JSON workflows under `backend/workflows/` select processors, detectors, and projections per use case.

## Layers

```
Angular (forjd.co)          Supabase Auth user JWT + WebCrypto seal
Partner SaaS (subprocessor)  Tenant-scoped service token (fjsvc_… / M2M JWT)
        │
        ▼
FastAPI (forjd-backend)     Principal verify (user vs service), tenancy, Prefect
        │  metadata only
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
| Sealed ingest API | FastAPI → Postgres (ciphertext-only); user JWT or tenant service token |
| Crypto sessions / replay / status / analytics | FastAPI + `require_tenant_access` (human member **or** scoped `fjsvc_`) |
| Daemon ingest (API key) | Rust `FORJD_ROLE=ingest` → outbox (sealed envelopes required) |
| Rollup + size/rate detectors | Rust `run_sealed_pipeline` (Pathway fallback) |
| Outbox → Streams, probes, cron | Rust data plane |
| Batch analytics / ML / SOC domain | Python (Polars / Prefect / optional torch) |
| Realtime UI | Supabase Realtime on `stream_results` / `telemetry_events` metadata |

## E2EE invariants

- Envelope: `algo`, `key_id`, `nonce`, `ciphertext`, optional `ratchet_header`
- AAD binds `tenant_id|client_event_id` (client-side)
- Unique `(tenant_id, key_id, nonce)` — rejects GCM nonce reuse (`sql/013`)
- `crypto_sessions` stores **public** X25519 keys only; `revoked_at` blocks ingest
- Pathway / Rust pipeline never receive ciphertext fields
- Internode AES-GCM on Dragonfly Streams is **transport** crypto (server-held keys), not client E2EE

## Configurable pipelines

```yaml
pipeline:
  processor: sealed_metadata   # or rust_sealed_metadata
  steps: [rollup, size_anomaly, rate_anomaly]
```

Processors resolve via `app.workflows.processors.REGISTRY`. Detectors via
`app.workflows.detectors.REGISTRY`. Add a vertical by dropping YAML — do not fork ingest.

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
  status management, and analytics reads (see `AUTH.md`).
- Details, scopes, and minting API: [`backend/docs/AUTH.md`](backend/docs/AUTH.md).

## SQL apply order

`003` → `019` under `backend/sql/` (see that folder’s README). Production forces
`SOFT_MIGRATE_SCHEMA=false`, `REQUIRE_RLS=true`, `REQUIRE_CRYPTO_SESSION=true`.
Realtime + `projection_feed` land in `015`; ML scores/runs in `016`; service-principal
session actor + expanded default scopes in `017`; partner domain scopes + erase in `018`;
erase opt-in defaults in `019`.

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
| `ingest` | Sealed edge → Postgres outbox | + `DATABASE_URL`, `REDIS_URL` |
| `relay` / `scheduler` / `normalizer` | Bus workers | + DSNs + **internode keys** |
| `all` | Relay + scheduler + probe + normalizer + ingest | DSNs + internode keys |

On Fly, bus roles default to `FORJD_INTERNODE_ENCRYPTION=required`. Set
`FORJD_INTERNODE_ACTIVE_KID` / `FORJD_INTERNODE_KEYS` with
[`scripts/sync_engine_dataplane_secrets.sh`](scripts/sync_engine_dataplane_secrets.sh).
Process-only mode: `fly secrets set FORJD_ROLE=engine -a forjd-engine`.

End-to-end partner path: partner BFF → FORJD API (`fjsvc_`) →
Supabase Postgres (ciphertext + projections) → optional engine sealed pipeline
via `ENGINE_URL`.

## Explicit non-goals

- Accepting partner SaaS end-user tokens at the FORJD edge
- Server-side plaintext ML on sealed payloads
- Python reimplementation of Rust relay / probe / normalizer / scheduler
- Product-specific workflow or event names in `app/` / `engine/` (YAML only)
