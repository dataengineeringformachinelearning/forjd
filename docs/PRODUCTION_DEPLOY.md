# Production deploy — FORJD (Fly + Vercel)

Final operator runbook for the FORJD platform. Partner BFF/UI steps live in the
partner repo (DEML: `docs/PRODUCTION_DEPLOY.md`).

**Verified live (2026-07-18):**

| Check | Result |
|-------|--------|
| `https://backend.forjd.co/health` | `healthy` / production |
| `https://backend.forjd.co/ready` | postgres + redis + `schema_rls=true` + engine ok |
| Engine | `forjd_role=All`, data_plane enabled, `/ready` 200 |
| Fly apps | `forjd-backend`, `forjd-engine`, `forjd-dragonfly` started (iad) |

---

## 1. Schema (Supabase)

```bash
cd backend
# Requires POSTGRES_DSN / DATABASE_URL in env (never commit)
uv run python scripts/apply_sql_migrations.py   # 003 → 019

POSTGRES_DSN='…' uv run python scripts/verify_supabase_post_migration.py
```

After `017`–`019`, remint partner tokens:

```bash
export FORJD_API_URL=https://backend.forjd.co
export FORJD_HUMAN_JWT='…'   # human owner/admin
export FORJD_TENANT_ID='…'
./scripts/remint_service_account.sh partner-production
# FORJD_INCLUDE_ERASE=1 (default) includes tenants:erase for account deletion
```

---

## 2. Fly.io — API (`forjd-backend`)

From **repo root** (Dockerfile builds Rust wheel):

```bash
# From repo root — config is fly.api.toml (Dockerfile: backend/Dockerfile)
fly deploy -a forjd-backend -c fly.api.toml
# Secrets (once): POSTGRES_DSN, REDIS_URL, SUPABASE_*, ENGINE_URL,
# ENGINE_API_TOKEN, ENVIRONMENT=production, CORS_ORIGINS including https://forjd.co
```

```bash
curl -fsS https://backend.forjd.co/health
curl -fsS https://backend.forjd.co/ready
fly checks list -a forjd-backend
```

---

## 3. Fly.io — Engine (`forjd-engine`)

```bash
cd engine
fly deploy -a forjd-engine
# FORJD_ROLE=all needs DSNs + internode keys:
#   ../scripts/sync_engine_dataplane_secrets.sh
curl -fsS https://forjd-engine.fly.dev/ready
```

Private URL for API: `http://forjd-engine.internal:8080`.

---

## 4. Vercel — FORJD web (`forjd.co`)

```bash
cd frontend
npx vercel link --project forjd --yes   # adjust project name if different
# apiBaseUrl = https://backend.forjd.co (see frontend env / vercel.json)
npx vercel deploy --prod --yes
```

Optional Storybook: `ui.forjd.co` (separate Vercel project).

DNS: `backend.forjd.co` → Fly `forjd-backend` (`fly certs add backend.forjd.co`).

---

## 5. Rollback

| Issue | Action |
|-------|--------|
| Bad API deploy | `fly releases -a forjd-backend` → prior image (SQL forward-only) |
| Bad engine deploy | Prior engine release; or `FORJD_ROLE=engine` (process-only) |
| Ingest errors | Check `/ready`, Dragonfly, crypto sessions, workflow YAML |
| Scope 403s | Remint `fjsvc_` (defaults do not rewrite existing rows) |
| Partner freeze | Partner sets write/read `off`; ciphertext remains in Supabase |

Do not soft-migrate schema in prod. Do not accept `service_role` JWTs.

---

## 6. Sealed-path smoke (service token)

1. `POST /api/v1/sessions` — register X25519 pubs (`sessions:write`).
2. `POST /api/v1/ingest` — AES-256-GCM envelopes only.
3. `GET /api/v1/projections` — scores/metadata (no ciphertext).
4. Status CRUD + analytics overview as scoped.
5. Staging: `POST /api/v1/tenants/{id}/erase` with `tenants:erase`.

---

## Production readiness

| Surface | Ready? |
|---------|--------|
| API + RLS | **Yes** |
| Engine data plane (`All`) | **Yes** |
| Dragonfly | **Yes** |
| Universal (no DEML hardcoding) | **Yes** |
| sql/019 + remint | **Apply/remint on next deploy** |

**Verdict:** FORJD is production-ready. Apply `sql/019`, deploy latest `main`
(security/perf pass), remint partner tokens as needed, then partner BFFs stay on
phase-2 FORJD-only cutover.
