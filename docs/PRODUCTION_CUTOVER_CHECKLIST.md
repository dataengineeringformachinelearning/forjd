# Production cutover checklist — FORJD + DEML

Single ops checklist for the final DEML → FORJD cutover. No overlapping data planes.

| Layer | Owner | Host |
|-------|--------|------|
| Angular UI | DEML | **Vercel** project `deml` |
| Django BFF / Firebase identity | DEML | **Fly** `deml-backend` (Railway standby) |
| Sealed streaming, projections, ML, exports, vulns | FORJD | **Fly** `forjd-backend` + `forjd-engine` |
| Cache (data plane) | FORJD | **Fly** Dragonfly |
| Control-plane Postgres | DEML | Neon → Supabase schema `deml` |
| Data-plane Postgres | FORJD | Supabase `public` |

**Do not** run Redpanda, ClickHouse, deml-dragonfly, or DEML Rust workers in production.

---

## A. FORJD (Fly)

1. Apply SQL `003` → `018` on Supabase (includes service-principal scopes + erase).
2. Remint `fjsvc_` after `017`/`018` so stored scopes include sessions/replay/status/analytics/exports/vulns/integrations/`tenants:erase`:
   ```bash
   ./scripts/remint_service_account.sh partner-production
   ```
3. `fly secrets set` on `forjd-backend`: `DATABASE_URL`/`POSTGRES_DSN`, `REDIS_URL`, `SUPABASE_*`, `ENGINE_URL`, `ENGINE_API_TOKEN`, …
4. `fly deploy -a forjd-backend` and `fly deploy` from `engine/` (`FORJD_ROLE` as documented).
5. Verify: `curl -fsS https://backend.forjd.co/ready` and `/health`.
6. Smoke: mint service account → sealed ingest → projections → analytics overview → status page CRUD → erase in staging.
7. Confirm `backend/scripts/apply_sql_migrations.py` includes `018` (or apply `018_partner_domain_scopes.sql` manually).

## B. DEML Fly + Vercel

1. Set Fly secrets on `deml-backend` (see `docs/FLY.md`):
   - `DATABASE_URL` (Neon or Supabase `deml` schema)
   - `FORJD_API_URL=https://backend.forjd.co`
   - **reminted** `FORJD_SERVICE_TOKEN` + `FORJD_TENANT_ID`
   - Firebase + Stripe + CORS origins for `deml.app` / Vercel
2. `cd backend && fly deploy`
3. `fly ssh console -a deml-backend -C "python manage.py map_forjd_tenant <account> <tenant> --service-token-secret-ref env:FORJD_SERVICE_TOKEN"`
4. Confirm `/api/v1/health` + `/api/v1/ready`.
5. Deploy Angular: Vercel project `deml` (`docs/VERCEL.md`); `BACKEND_URL=https://backend.deml.app`.
6. Cutover phases (optional dual-write first):
   ```bash
   fly secrets set FORJD_CUTOVER_PHASE=0 -a deml-backend   # dual-write / empty-read
   fly secrets set FORJD_CUTOVER_PHASE=1 -a deml-backend   # read FORJD
   fly secrets set FORJD_CUTOVER_PHASE=2 -a deml-backend   # FORJD-only (steady state)
   ```
7. Smoke Angular: login, dashboard CES, status pages, vulns list, exports list, sessions, account delete (staging).

## C. Retire legacy DEML Railway data plane

```bash
python scripts/railway_audit.py --apply --service deml-backend
python scripts/railway_retire_dataplane.py --apply   # includes deml-dragonfly
```

Keep Railway `deml-backend` / `deml-frontend` only as cold standby until DNS is stable on Fly/Vercel.

## D. Separation invariants (no overlaps)

| Concern | DEML | FORJD |
|---------|------|-------|
| End-user auth | Firebase | Supabase Auth (platform) / `fjsvc_` (partners) |
| Browser API | Django only | Never called with Firebase tokens |
| Ingest / projections / ML | BFF → FORJD | Owns storage + processing |
| Sessions (browser) | Postgres `browser_sessions` | Crypto sessions (E2EE) |
| Cache | None required | Fly Dragonfly |
| Tenant erase | Calls FORJD erase then local teardown | `POST /api/v1/tenants/{id}/erase` |
