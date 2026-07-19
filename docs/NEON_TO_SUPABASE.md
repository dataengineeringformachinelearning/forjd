# Partner control-plane co-location (Neon → Supabase)

Goal: keep FORJD data plane on Supabase `public`, and optionally co-locate a
**partner control-plane** database into the same Supabase project under a
non-`public` schema.

## Current state

| System | Database | Notes |
|--------|----------|-------|
| **FORJD** (`forjd-backend` / `forjd-engine`) | **Supabase** (`POSTGRES_DSN`) | `pgcrypto`, `vector`, RLS, Realtime; `/ready` → `schema_rls=true` |
| **Partner control plane** (optional) | Often a separate Neon/Postgres | Identity, billing, consent — never write into FORJD `public` |

**Implication:** FORJD does **not** need a Neon→Supabase data move for its own tables.
Consolidation means migrating a partner control-plane DB into a dedicated schema
(for example `partner_control`) or keeping it on a separate host.

Major PG version downgrades (e.g. Neon 18 → Supabase 17) are risky. Prefer:

1. Partner `dumpdata` / `loaddata` (version-agnostic), **or**
2. Wait until Supabase matches the source major, **or**
3. `ALLOW_MAJOR_DOWNGRADE=1` only after a successful dry-run restore into a throwaway DB.

---

## Exact commands (pg_dump / pg_restore)

### 0. Prerequisites

```bash
# Client tools matching ≥ target major (17+)
brew install libpq && brew link --force libpq   # macOS
# or: apt install postgresql-client-17

# Collect URLs from consoles (do not commit):
# Source:  provider connection string (direct, sslmode=require)
# Supabase: Project Settings → Database → URI
#   Direct (restore):  postgresql://postgres.[ref]:[pass]@db.[ref].supabase.co:5432/postgres
#   Pooler (app):      postgresql://postgres.[ref]:[pass]@aws-0-[region].pooler.supabase.com:6543/postgres
```

### 1. Dry-run dump from source

```bash
cd /path/to/forjd
export NEON_DATABASE_URL='postgresql://…@….neon.tech/neondb?sslmode=require'
export SUPABASE_DATABASE_URL='postgresql://postgres.…@db.…supabase.co:5432/postgres'

chmod +x scripts/pg_migrate_neon_to_supabase.sh
DRY_RUN=1 MIGRATE_MODE=partner TARGET_SCHEMA=partner_control \
  ./scripts/pg_migrate_neon_to_supabase.sh
# → writes .pg_migrate_dumps/neon_partner_*.dump (no restore)
```

### 2. Enable extensions on Supabase (idempotent)

Dashboard → Database → Extensions → enable **pgcrypto**, **vector**  
or via SQL (script also does this):

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3. Restore partner tables into a non-public schema

```bash
MIGRATE_MODE=partner TARGET_SCHEMA=partner_control \
  ./scripts/pg_migrate_neon_to_supabase.sh
```

Never restore partner tables into `public` — that collides with FORJD tenants,
`stream_results`, and RLS policies.

### 4. Point the partner app

Use the Supabase **pooler** URI for the partner Django/API process and set
`search_path` to include the partner schema first (e.g. `partner_control,public`).

### 5. Verify FORJD gates

```bash
POSTGRES_DSN='postgresql://…' \
  python backend/scripts/verify_supabase_post_migration.py

# Optional: also report partner schema presence
PARTNER_CONTROL_SCHEMA=partner_control POSTGRES_DSN='postgresql://…' \
  python backend/scripts/verify_supabase_post_migration.py
```

Keep the source database read-only for ≥ 7 days before delete. Rollback is
repointing the partner `DATABASE_URL` at the original host.

Partner-specific cutover steps (BFF flags, DNS, Railway retirement) live in the
partner repository — not here.
