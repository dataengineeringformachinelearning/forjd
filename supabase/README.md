# Supabase (Auth · Postgres · Realtime · Edge Functions)

FORJD uses Supabase as the sole identity + primary database plane.

## Apply SQL

Run `backend/sql/003` → `013` in the SQL editor (see `backend/sql/README.md`).

## Realtime

Enable replication for consumer-facing tables (Dashboard → Database → Replication):

- `stream_results` — scores / rollups (no ciphertext)
- `telemetry_events` — optional; clients decrypt locally using their keys

## Edge Functions

```bash
supabase functions deploy peer-sessions
```

`peer-sessions` lists non-revoked X25519 **public** keys for a tenant (JWT required).
FastAPI `GET /api/v1/sessions` remains the primary API; the Edge Function is for
low-latency peer discovery from the browser.
