# FORJD Architecture

Universal secure streaming platform. Stability and E2EE over novelty.

## Principles

1. **Supabase-first** — Postgres + pgvector + Auth + Realtime. No ClickHouse. No Firebase.
2. **Rust-max hot path** — ingestion edge, sealed-metadata pipeline, outbox/relay, probes, scheduling live in `forjd-engine`.
3. **Ciphertext-blind server** — Signal-inspired: AES-256-GCM envelopes, X25519/HKDF session keys client-side; server stores ciphertext + opaque ratchet headers only.
4. **Config over forks** — YAML/JSON workflows under `backend/workflows/` select processors, detectors, and projections per SaaS use case.

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
`app.workflows.detectors.REGISTRY`. Add a SaaS vertical by dropping YAML — do not fork ingest.

Partner / legacy wire ids are also config-only:

```yaml
aliases:
  workflow_ids: [partner_legacy_id]
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

`003` → `016` under `backend/sql/` (see that folder’s README). Production forces
`SOFT_MIGRATE_SCHEMA=false`, `REQUIRE_RLS=true`, `REQUIRE_CRYPTO_SESSION=true`.
Realtime + `projection_feed` land in `015`; service-principal session actor +
expanded default scopes in `016`.

## Production cutover

Operator checklist (preflight, dual-write → read switch → write switch →
decommission, rollback): [`CUTOVER.md`](CUTOVER.md).

## Explicit non-goals

- ClickHouse / Redpanda / Firebase / Firestore **as FORJD identity or OLAP**
- Accepting partner SaaS end-user tokens at the FORJD edge
- Server-side plaintext ML on sealed payloads
- Python reimplementation of Rust relay / probe / normalizer / scheduler
- Product-specific workflow or event names in `app/` / `engine/` (YAML only)
