# FORJD Supabase SQL

Apply in order in the Supabase SQL editor (or `psql`).

| File | Purpose |
|------|---------|
| `001_pulses.sql` | Stack pulse PoC |
| `002_anomaly_embeddings.sql` | Legacy ML PoC embeddings |
| `003_secure_tenancy.sql` | **Production path** — tenants, RLS, E2EE telemetry, vector embeddings |
| `004_crypto_sessions.sql` | X25519 public-key session directory (private keys never stored) |

## Secure path (`003` + `004`)

1. Enable extensions **vector** and **pgcrypto** (Dashboard → Database → Extensions).
2. Run `003_secure_tenancy.sql`, then `004_crypto_sessions.sql`.
3. Optional Realtime: Dashboard → Replication → add `telemetry_events`.
4. Set backend env: `SUPABASE_URL`, `SUPABASE_JWT_SECRET` (or rely on JWKS), `POSTGRES_DSN`.

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
| Pathway | Rolls up metadata (counts / sizes), never decrypts |

Plaintext never crosses the API on the E2EE path.
