# Production cutover checklist — FORJD

FORJD-only ops checklist for partner cutover. Partner BFF / UI runbooks live in the
partner repository (example: DEML `docs/PRODUCTION_CUTOVER_CHECKLIST.md`).

| Layer | Owner | Host |
|-------|--------|------|
| Sealed streaming, projections, ML, exports, vulns, status | FORJD | **Fly** `forjd-backend` + `forjd-engine` |
| Cache (data plane) | FORJD | **Fly** Dragonfly (`forjd-dragonfly`) |
| Data-plane Postgres | FORJD | Supabase `public` (+ RLS / Realtime) |
| Partner user plane | Partner | Partner hosts (e.g. Fly Django + Vercel Angular) |

**Do not** run Redpanda, ClickHouse, Kafka, or partner-local stream workers as a FORJD substitute.

---

## A. Schema + service principals

1. Apply SQL `003` → `018` on Supabase (includes service-principal scopes + erase).
2. Remint `fjsvc_` after `017`/`018` so stored scopes include sessions/replay/status/analytics/exports/vulns/integrations/`tenants:erase`:
   ```bash
   ./scripts/remint_service_account.sh partner-production
   ```
3. Confirm `backend/scripts/apply_sql_migrations.py` includes `018` (or apply `018_partner_domain_scopes.sql` manually).

## B. Fly deploy

1. `fly secrets set` on `forjd-backend`: `DATABASE_URL`/`POSTGRES_DSN`, `REDIS_URL`, `SUPABASE_*`, `ENGINE_URL`, `ENGINE_API_TOKEN`, …
2. `fly deploy -a forjd-backend` and `fly deploy` from `engine/` (`FORJD_ROLE` as documented).
3. Engine data plane (`FORJD_ROLE=all`) needs internode keys via `scripts/sync_engine_dataplane_secrets.sh`.
4. Verify: `curl -fsS https://backend.forjd.co/ready` and `/health`.
5. Optional gates: `POSTGRES_DSN=… python backend/scripts/verify_supabase_post_migration.py`.

## C. Partner smoke (universal)

1. Mint service account → sealed ingest → projections list.
2. Analytics overview → status page CRUD → exports/vulns as scoped.
3. Staging tenant erase: `POST /api/v1/tenants/{id}/erase`.
4. Partner BFF advances its own dual-write/read flags (never hardcoded product names in FORJD).

## D. Separation invariants

| Concern | Partner | FORJD |
|---------|---------|-------|
| End-user auth | Partner IdP (e.g. Firebase) | Supabase Auth (platform) / `fjsvc_` (partners) |
| Browser API | Partner BFF only | Never called with partner end-user tokens |
| Ingest / projections / ML | BFF → FORJD | Owns storage + processing |
| Cache | Optional / none | Fly Dragonfly |
| Tenant erase | Calls FORJD erase then local teardown | `POST /api/v1/tenants/{id}/erase` |
