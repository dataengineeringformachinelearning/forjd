# Neon → Supabase Postgres consolidation

Goal: one Postgres for FORJD (and optional DEML control-plane co-location).

## Current state (verified 2026-07-18)

| System | Database today | PG | Notes |
|--------|----------------|----|-------|
| **FORJD** (`forjd-backend` / `forjd-engine`) | **Supabase already** (`*.pooler.supabase.com` / project `adsmmikjthfufjocmpty`) | **17.6** | `pgcrypto`, `vector`, RLS, Realtime present; `/ready` → `schema_rls=true` |
| **DEML** (Railway `DATABASE_URL`) | Neon project `deml` (`summer-king-74177511`) | **18.4** | Django control plane (~395 MB); **no** `vector`; overlaps table names with FORJD (`status_pages`, `training_runs`, …) |

**Implication:** FORJD does **not** need a Neon→Supabase data move. Consolidation means migrating **DEML’s Neon DB** into the same Supabase project under schema `deml` (or keeping DEML on Neon until PG majors align).

Neon PG **18** → Supabase PG **17** is a **major downgrade**. Prefer:

1. Django `dumpdata` / `loaddata` for DEML (version-agnostic), **or**
2. Wait until the Supabase project is on PG 18, **or**
3. `ALLOW_MAJOR_DOWNGRADE=1` only after a successful dry-run restore into a throwaway DB.

---

## Exact commands (pg_dump / pg_restore)

### 0. Prerequisites

```bash
# Client tools matching ≥ target major (17+)
brew install libpq && brew link --force libpq   # macOS
# or: apt install postgresql-client-17

# Collect URLs from consoles (do not commit):
# Neon:    console.neon.tech → Connection string (direct, sslmode=require)
# Supabase: Project Settings → Database → URI
#   Direct (restore):  postgresql://postgres.[ref]:[pass]@db.[ref].supabase.co:5432/postgres
#   Pooler (app):      postgresql://postgres.[ref]:[pass]@aws-0-[region].pooler.supabase.com:6543/postgres
```

### 1. Dry-run dump from Neon

```bash
cd /path/to/forjd
export NEON_DATABASE_URL='postgresql://…@….neon.tech/neondb?sslmode=require'
export SUPABASE_DATABASE_URL='postgresql://postgres.…@db.…supabase.co:5432/postgres'

chmod +x scripts/pg_migrate_neon_to_supabase.sh
DRY_RUN=1 MIGRATE_MODE=deml ./scripts/pg_migrate_neon_to_supabase.sh
# → writes .pg_migrate_dumps/neon_deml_*.dump (no restore)
```

### 2. Enable extensions on Supabase (idempotent)

Dashboard → Database → Extensions → enable **pgcrypto**, **vector**  
or via SQL (script also does this):

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3. Restore DEML into schema `deml` (recommended)

```bash
# Requires Docker for staging rename public → deml
MIGRATE_MODE=deml ./scripts/pg_migrate_neon_to_supabase.sh
```

This:

1. `pg_dump --format=custom --schema=public` from Neon  
2. Restores into local `postgres:17` staging  
3. `ALTER SCHEMA public RENAME TO deml`  
4. `pg_dump --schema=deml` → `pg_restore` into Supabase  
5. Grants usage to Supabase roles  

**Do not** restore DEML into `public` — it will collide with FORJD tables.

### 4. FORJD disaster-recovery path only

Only if you have a Neon copy of FORJD tables to merge into `public`:

```bash
# Dangerous if Supabase already has FORJD objects — prefer empty target or --clean lab DB
MIGRATE_MODE=forjd ALLOW_MAJOR_DOWNGRADE=1 ./scripts/pg_migrate_neon_to_supabase.sh
```

Production FORJD should keep applying `backend/sql/003`→`017` instead of dumping Neon.

### 5. Alternative for DEML (avoids PG 18→17 dump issues)

```bash
# On Railway / local with Neon DATABASE_URL:
cd dataengineeringformachinelearning/backend
python manage.py dumpdata \
  --natural-foreign --natural-primary \
  -o /tmp/deml_neon.json

# Point DATABASE_URL at Supabase (search_path=deml,public), migrate schema, then:
python manage.py loaddata /tmp/deml_neon.json
```

---

## Cutover (minimal downtime)

```text
T-0   DRY_RUN dump; verify dump size; run verify script against live Supabase (FORJD)
T+1   Put DEML Django in maintenance / read-only (or short freeze writes)
T+2   Final Neon dump + restore into Supabase schema deml
T+3   Flip DEML DATABASE_URL → Supabase (pooler :6543) with search_path
T+4   Run Django migrate --check; smoke auth/billing/FORJD mapping
T+5   Re-enable writes; monitor 24–72h
T+7d  Decommission Neon after rollback window
```

FORJD Fly secrets already use Supabase — **no DSN flip** unless you change projects.

### FORJD connection strings (confirm / set)

```bash
# App (asyncpg form on Fly)
fly secrets set \
  POSTGRES_DSN='postgresql+asyncpg://postgres.[ref]:[pass]@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require' \
  -a forjd-backend

# Engine (libpq form; sync script copies from backend)
./scripts/sync_engine_dataplane_secrets.sh
```

### DEML Railway (after schema `deml` restore)

```bash
# Pooler for app traffic; include search_path so deml is default
railway variable set \
  DATABASE_URL='postgresql://postgres.[ref]:[pass]@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require&options=-csearch_path%3Ddeml%2Cpublic' \
  --service deml-backend
```

Django settings should keep using `DATABASE_URL` (dj-database-url). If `options` is awkward on Railway, set:

```python
# backend/config/settings.py (only if needed)
DATABASES["default"]["OPTIONS"] = {
  "options": "-c search_path=deml,public"
}
```

---

## Post-migration verification

### FORJD (required)

```bash
# Local / CI with DSN:
POSTGRES_DSN='postgresql://…@db.…supabase.co:5432/postgres' \
  python backend/scripts/verify_supabase_post_migration.py

# Or on Fly (after deploy that includes the script):
fly ssh console -a forjd-backend -C \
  'sh -c "cd /app && .venv/bin/python scripts/verify_supabase_post_migration.py"'

curl -sS https://backend.forjd.co/ready
# expect: postgres+redis+schema_rls true; engine.ok true
```

Checks covered: `pgcrypto`/`vector`, core tables, RLS flags, `supabase_realtime` publication, `projection_feed` / `sealed_events`, optional `deml` schema presence.

### Manual SQL (Supabase SQL editor)

See [`scripts/verify_supabase_post_migration.sql`](../scripts/verify_supabase_post_migration.sql).

### Realtime

1. Dashboard → Database → Replication: `stream_results` / `telemetry_events` / `ml_scores` as needed  
2. `015_realtime_and_consumer.sql` / `016_ml_supabase.sql` already add publication membership when `supabase_realtime` exists  
3. Browser: subscribe with anon key + user JWT; confirm events

### RLS smoke

```sql
-- As service_role (Dashboard) should see rows; as anon without JWT should not.
SET ROLE authenticated;
SELECT count(*) FROM public.telemetry_events;  -- expect 0 / denied without JWT claims
RESET ROLE;
```

---

## Rollback

| Symptom | Action |
|---------|--------|
| DEML broken after flip | `railway variable set DATABASE_URL=<neon-url> --service deml-backend` and redeploy/restart |
| FORJD API errors after accidental DSN change | Restore previous Fly secret: `fly secrets set POSTGRES_DSN=<prior-supabase-or-neon> -a forjd-backend` |
| Partial `deml` schema restore | `DROP SCHEMA deml CASCADE;` on Supabase (FORJD `public` untouched), re-run migrate |
| Keep Neon | Leave Neon **read-only** (scale compute to 0.25 / restrict writers) for ≥ 7 days before delete |

Neon rollback requires the Neon project still exists and `DATABASE_URL` secret retained offline.

---

## Idempotency notes

- `CREATE EXTENSION IF NOT EXISTS` — safe to re-run  
- `MIGRATE_MODE=deml` uses a new staging container each run; re-running restore into existing `deml` may conflict — drop schema first or restore into `deml_YYYYMMDD`  
- FORJD SQL `003`–`017` remain the source of truth for `public` schema (re-apply via `scripts/apply_sql_on_fly.sh`)  

---

## Related

- SQL order: [`backend/sql/README.md`](../backend/sql/README.md)  
- Cutover: [`CUTOVER.md`](../CUTOVER.md)  
- Engine DSN sync: [`scripts/sync_engine_dataplane_secrets.sh`](../scripts/sync_engine_dataplane_secrets.sh)  
