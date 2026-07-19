# Production checklist — FORJD

Operator checklist for the FORJD platform. Partner BFF / UI steps live in the
partner repo. Deploy commands: [`PRODUCTION_DEPLOY.md`](./PRODUCTION_DEPLOY.md).

| Layer | Owner | Host |
|-------|--------|------|
| Sealed streaming, projections, ML, exports, vulns, status | FORJD | Fly `forjd-backend` + `forjd-engine` |
| Cache (data plane) | FORJD | Fly Dragonfly (`forjd-dragonfly`) |
| Data-plane Postgres | FORJD | Supabase `public` (+ RLS / Realtime) |
| Partner user plane | Partner | Partner hosts |

---

## A. Schema + service principals

| Step | Action |
|------|--------|
| A1 | Apply SQL `003` → `019` |
| A2 | Mint `fjsvc_` (`scripts/remint_service_account.sh` or mint API) |
| A3 | Confirm `/ready` reports `schema_rls=true` |

```bash
./scripts/remint_service_account.sh partner-production
```

## B. Fly deploy

| Step | Action |
|------|--------|
| B1 | Secrets on `forjd-backend` (`POSTGRES_DSN`, `REDIS_URL`, `SUPABASE_*`, `ENGINE_*`, `ENVIRONMENT=prod`) |
| B2 | Deploy API + engine (`FORJD_ROLE=all` + internode keys) |
| B3 | Confirm `https://backend.forjd.co/ready` |
| B4 | Optional `verify_supabase_post_migration.py` after schema apply |

## C. Partner smoke

1. Mint service account → sealed ingest → projections list.
2. Analytics overview → status page CRUD → exports/vulns as scoped.
3. Staging tenant erase: `POST /api/v1/tenants/{id}/erase`.

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
