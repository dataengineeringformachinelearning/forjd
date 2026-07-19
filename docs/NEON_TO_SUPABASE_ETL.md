# Neon → Supabase controlled ETL (production)

Configurable, resumable ETL for migrating a **partner control-plane** Postgres
(typically Neon) into Supabase under a **non-`public` schema**. This is the
preferred path when you need field mapping, filters, transforms, pgvector
handling, or incremental catch-up — not a blind dump/restore.

Dump/restore remains available as a fallback:
[`docs/NEON_TO_SUPABASE.md`](NEON_TO_SUPABASE.md) +
`scripts/pg_migrate_neon_to_supabase.sh`.

## What this does

| Concern | Behavior |
|---------|----------|
| Schema | `CREATE EXTENSION`, `CREATE SCHEMA`, `CREATE TABLE IF NOT EXISTS`, additive `ALTER TABLE … ADD COLUMN` |
| Data | Batched `SELECT` → row transforms → `INSERT … ON CONFLICT DO UPDATE` (PK upsert) |
| pgvector | Preserves `vector(n)` via `format_type`; optional dimension checks in YAML |
| Filters | Per-table SQL `WHERE` fragments + bind params (`tenant_id`, `since`, `until`) |
| Idempotent | Upserts on primary key; re-runs update existing rows |
| Resumable | Watermarks in `{target_schema}._etl_checkpoints` (keyset pagination) |
| Modes | `full` (skip if already `completed`) or `incremental` (advance watermark) |
| Ops | Structured logging, per-batch progress, retries on operational errors |

**Hard rule:** `target.schema` must never be `public`. FORJD RLS and stream
tables own `public`.

## Layout

```
scripts/neon_supabase_etl/
  config.example.yaml      # copy → config.local.yaml (gitignored)
  neon_to_supabase.py      # migrate CLI
  verify_etl.py            # post-migration checks
  forjd_etl/               # package (config, schema, transfer, state, …)
```

## Environment variables

| Variable | Required | Notes |
|----------|----------|-------|
| `NEON_DATABASE_URL` or `SOURCE_DATABASE_URL` | yes | Source (Neon) direct URI, `sslmode=require` |
| `SUPABASE_DATABASE_URL` or `TARGET_DATABASE_URL` | yes | Supabase **direct** `db.<ref>.supabase.co:5432` — **not** pooler `:6543` |

Never commit DSNs. Put them in your shell or a local untracked env file.

## Install

```bash
cd backend
uv sync --group etl
```

Optional: `uv sync --group etl --locked` in CI.

## Configure

```bash
cp scripts/neon_supabase_etl/config.example.yaml \
   scripts/neon_supabase_etl/config.local.yaml
# Edit tables, primary keys, filters, transforms, vector_columns
```

YAML highlights:

- `tables[].columns` — optional source→target rename map (`null` = all columns)
- `tables[].exclude_columns` — drop columns from the transfer
- `tables[].filter` — SQL fragment, e.g. `tenant_id = %(tenant_id)s::uuid AND updated_at >= %(since)s`
- `tables[].transforms` — `strip` / `lower` / `upper` / `map` / `const` / `json_dumps` / `null_if_empty`
- `tables[].vector_columns` — mark embedding columns; optional `dimensions`
- `tables[].incremental.column` — watermark column for resume / delta sync
- `params` — default bind values; CLI can override

## Commands

### Dry-run (no writes)

```bash
cd backend
export NEON_DATABASE_URL='postgresql://…'
export SUPABASE_DATABASE_URL='postgresql://postgres.…@db.…supabase.co:5432/postgres'

uv run --group etl python ../scripts/neon_supabase_etl/neon_to_supabase.py \
  --config ../scripts/neon_supabase_etl/config.local.yaml \
  --dry-run -v
```

### Full migration

```bash
uv run --group etl python ../scripts/neon_supabase_etl/neon_to_supabase.py \
  --config ../scripts/neon_supabase_etl/config.local.yaml \
  --mode full -v
```

### Single table / reset checkpoint

```bash
uv run --group etl python ../scripts/neon_supabase_etl/neon_to_supabase.py \
  --config ../scripts/neon_supabase_etl/config.local.yaml \
  --table auth_user --reset -v
```

### Incremental (delta) sync

After the initial full load, keep the source online and catch up:

```bash
uv run --group etl python ../scripts/neon_supabase_etl/neon_to_supabase.py \
  --config ../scripts/neon_supabase_etl/config.local.yaml \
  --mode incremental \
  --since '2026-07-01T00:00:00+00:00' \
  --tenant-id 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' \
  -v
```

Incremental uses `tables[].incremental.column` (or PK) as a **strictly greater
than** watermark. Deletions on the source are **not** mirrored — handle soft
deletes or a separate purge if required.

### Verify

```bash
uv run --group etl python ../scripts/neon_supabase_etl/verify_etl.py \
  --config ../scripts/neon_supabase_etl/config.local.yaml -v
```

Also keep FORJD platform gates green:

```bash
POSTGRES_DSN="$SUPABASE_DATABASE_URL" \
  python backend/scripts/verify_supabase_post_migration.py
```

## Minimal-downtime switch

1. **Prep** — Enable `pgcrypto` / `vector` on Supabase; copy YAML; dry-run.
2. **Initial full load** — Run `--mode full` while the partner app still uses Neon.
   Expect long-running batches; safe to re-run (resumes from checkpoint).
3. **Freeze writes** (short window) — Put partner API in read-only / maintenance,
   or stop writers. Note the freeze timestamp `T`.
4. **Final incremental** — `--mode incremental` (optionally `--since T` in filters)
   until watermarks catch up and verify passes.
5. **Cut DNS/DSN** — Point partner `DATABASE_URL` at Supabase **pooler** with
   `search_path` including `partner_control` (or your target schema) first.
6. **Hold Neon** — Keep source read-only ≥ 7 days before decommission.
7. **Rollback** — Repoint partner `DATABASE_URL` to Neon; FORJD `public` is untouched.

Do **not** point FORJD `POSTGRES_DSN` at a partner schema. FORJD continues to use
Supabase `public` exclusively.

## Operational caveats

- Concurrent source writes during a batch can race; for zero-loss switch use the
  freeze + final incremental window above.
- Major version downgrades (e.g. PG18 → PG17) may reject DDL/types — prefer
  matching majors or application-level serializers for problematic types.
- Checkpoints live in the **target** DB; deleting `{schema}._etl_checkpoints`
  or using `--reset` forces a re-scan from the start of the watermark keyspace.
- Row-level errors are logged; set `options.max_table_errors` to fail closed.

## Tests

```bash
cd backend
uv sync --group etl
PYTHONPATH=../scripts/neon_supabase_etl \
  uv run python -m unittest tests.test_neon_supabase_etl -v
```
