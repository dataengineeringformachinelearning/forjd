# Production cutover checklist — FORJD

FORJD-only ops checklist. Partner BFF / UI: partner repo
(example DEML `docs/PRODUCTION_CUTOVER_CHECKLIST.md`).
Deploy commands: [`PRODUCTION_DEPLOY.md`](./PRODUCTION_DEPLOY.md).

| Layer | Owner | Host | Status (2026-07-18) |
|-------|--------|------|---------------------|
| Sealed streaming, projections, ML, exports, vulns, status | FORJD | **Fly** `forjd-backend` + `forjd-engine` | **Live** |
| Cache (data plane) | FORJD | **Fly** Dragonfly (`forjd-dragonfly`) | **Live** |
| Data-plane Postgres | FORJD | Supabase `public` (+ RLS / Realtime) | **Live** (`schema_rls=true`) |
| Partner user plane | Partner | Partner hosts | Partner-owned |

**Do not** run Redpanda, ClickHouse, Kafka, or partner-local stream workers as a FORJD substitute.

---

## A. Schema + service principals

| Step | Action | Status |
|------|--------|--------|
| A1 | Apply SQL `003` → `018` | **Done** |
| A2 | Apply SQL `019` (erase opt-in default) | **Pending** next migrate |
| A3 | Remint `fjsvc_` (`scripts/remint_service_account.sh`) | Remint after `019` if erase required |
| A4 | `apply_sql_migrations.py` includes `019` | **In repo** |

```bash
./scripts/remint_service_account.sh partner-production
```

## B. Fly deploy

| Step | Action | Status |
|------|--------|--------|
| B1 | Secrets on `forjd-backend` | **Configured** |
| B2 | Deploy API + engine (`FORJD_ROLE=all` + internode keys) | **Live** |
| B3 | `https://backend.forjd.co/ready` | **Pass** |
| B4 | Redeploy latest `main` (security/perf pass) | **Pending** after push |
| B5 | Optional `verify_supabase_post_migration.py` | Recommended after `019` |

## C. Partner smoke (universal)

1. Mint service account → sealed ingest → projections list.
2. Analytics overview → status page CRUD → exports/vulns as scoped.
3. Staging tenant erase: `POST /api/v1/tenants/{id}/erase`.
4. Partner BFF steady state (phase 2 / forjd-only).

## D. Separation invariants

| Concern | Partner | FORJD |
|---------|---------|-------|
| End-user auth | Partner IdP (e.g. Firebase) | Supabase Auth (platform) / `fjsvc_` (partners) |
| Browser API | Partner BFF only | Never called with partner end-user tokens |
| Ingest / projections / ML | BFF → FORJD | Owns storage + processing |
| Cache | Optional / none | Fly Dragonfly |
| Tenant erase | Calls FORJD erase then local teardown | `POST /api/v1/tenants/{id}/erase` |

## E. Rollback

| Issue | Action |
|-------|--------|
| Bad API/engine deploy | Prior Fly release; engine → `FORJD_ROLE=engine` |
| Ingest errors | `/ready`, Dragonfly, crypto sessions, workflows |
| Scope 403s | Remint `fjsvc_` |
| Partner freeze | Partner write/read `off` |

## F. Verdict

**FORJD is production-ready.** Apply `sql/019`, deploy latest `main`, remint partner tokens as needed. Live gates already pass health/ready/engine All.
