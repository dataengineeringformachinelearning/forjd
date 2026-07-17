# FORJD Supabase SQL

Apply in order in the Supabase SQL editor (or `psql`).

| File | Purpose |
|------|---------|
| `001_pulses.sql` | Stack pulse PoC |
| `002_anomaly_embeddings.sql` | Legacy ML PoC embeddings |
| `003_secure_tenancy.sql` | **Production path** — tenants, RLS, E2EE telemetry, vector embeddings |
| `004_crypto_sessions.sql` | X25519 public-key session directory (private keys never stored) |
| `005_stream_results.sql` | Pathway/Prefect outputs (metadata scores; RLS) |
| `006_universal_stream.sql` | `event_type` / `workflow_id`, `use_cases`, `sealed_events` view |
| `007_projections.sql` | Durable projections, checkpoints, DLQ |
| `008_status_pages.sql` | Status pages / services / incidents (public when published) |

## Secure path (`003`–`008`)

1. Enable extensions **vector** and **pgcrypto** (Dashboard → Database → Extensions).
2. Run `003` → `008` in order.
3. Optional Realtime: Dashboard → Replication → add `telemetry_events` and/or `stream_results`.
4. Set backend env: `SUPABASE_URL`, `SUPABASE_JWT_SECRET` (or rely on JWKS), `POSTGRES_DSN`.
5. Add SaaS use cases as YAML under `backend/workflows/` (see that folder’s README).

### Roles

| Client | How |
|--------|-----|
| Browser / Realtime | Supabase anon key + user JWT → RLS via `auth.uid()` |
| FastAPI ingest | Verify JWT → write with service-role DSN → membership checked in app |

### E2EE (Signal-inspired)

| Piece | Role |
|-------|------|
| X25519 ECDH + HKDF | Client derives per-session AES-256 keys |
| AES-256-GCM | Seals each event; AAD binds `tenant_id\|client_event_id` |
| Double Ratchet | Client-owned forward secrecy; `ratchet_header` opaque to server |
| `telemetry_events.ciphertext` | Encrypted payload only (server-blind) |
| `crypto_sessions` | Public keys for peer discovery — never private keys |
| Pathway | Rolls up metadata + size anomalies, never decrypts |
| `stream_results` | Consumer-facing scores/rollups (no ciphertext) |
| `use_cases` | Optional DB catalog of workflows |
| `sealed_events` | View alias over `telemetry_events` |

Plaintext never crosses the API on the E2EE path. Downstream SaaS (DEML, analytics,
threat, …) read `stream_results` (and optionally sealed events for client decrypt) under RLS.
