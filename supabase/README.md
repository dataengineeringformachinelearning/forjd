# Supabase (Auth · Postgres · Realtime · Edge Functions)

FORJD uses Supabase as the sole identity + primary database plane.

## Apply SQL

Run `backend/sql/003` → `015` in the SQL editor (see `backend/sql/README.md`).

## Realtime

Migration `015` adds these tables to the `supabase_realtime` publication when it
exists (confirm under Dashboard → Database → Replication):

- `stream_results` — scores / rollups (no ciphertext); preferred for UIs
- `telemetry_events` — optional; clients decrypt locally using their keys

Consumer clients may also select from the `projection_feed` view (same columns
as `stream_results`, RLS via `security_invoker`).

Subprocessors typically poll `GET /api/v1/projections?since=` with a
tenant `fjsvc_` token; browser UIs can subscribe with the user JWT + RLS.

## Edge Functions

```bash
supabase functions deploy peer-sessions
```

`peer-sessions` lists non-revoked X25519 **public** keys for a tenant (JWT required).
FastAPI `GET /api/v1/sessions` remains the primary API; the Edge Function is for
low-latency peer discovery from the browser.
