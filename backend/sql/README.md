# FORJD Supabase SQL

Apply in order in the Supabase SQL editor (or `psql`).

| File | Purpose |
|------|---------|
| `001_pulses.sql` | Stack pulse PoC |
| `002_anomaly_embeddings.sql` | Legacy ML PoC embeddings |
| `003_secure_tenancy.sql` | **Production path** — tenants, RLS, E2EE telemetry, vector embeddings |

## Secure path (`003`)

1. Enable extensions **vector** and **pgcrypto** (Dashboard → Database → Extensions).
2. Run `003_secure_tenancy.sql`.
3. Optional Realtime: Dashboard → Replication → add `telemetry_events`.
4. Set backend env: `SUPABASE_URL`, `SUPABASE_JWT_SECRET` (or rely on JWKS), `POSTGRES_DSN`.

### Roles

| Client | How |
|--------|-----|
| Browser / Realtime | Supabase anon key + user JWT → RLS via `auth.uid()` |
| FastAPI ingest | Verify JWT → write with service-role DSN → membership checked in app |

### E2EE

Clients encrypt with AES-256-GCM; server stores `ciphertext`, `nonce`, `key_id`, opaque `ratchet_header`. Plaintext never crosses the API on the E2EE path.
