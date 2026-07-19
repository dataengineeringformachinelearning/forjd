# Neon → Supabase ETL

Production-grade, configurable migration into a **non-`public`** Supabase schema.

Full runbook: [`docs/NEON_TO_SUPABASE_ETL.md`](../../docs/NEON_TO_SUPABASE_ETL.md).

```bash
cp config.example.yaml config.local.yaml
cd ../../backend && uv sync --group etl
export NEON_DATABASE_URL='…'
export SUPABASE_DATABASE_URL='…'   # direct :5432
uv run --group etl python ../scripts/neon_supabase_etl/neon_to_supabase.py \
  --config ../scripts/neon_supabase_etl/config.local.yaml --dry-run -v
```
