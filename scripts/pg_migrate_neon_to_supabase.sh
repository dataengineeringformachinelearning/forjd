#!/usr/bin/env bash
# Neon → Supabase Postgres migration helper (pg_dump / pg_restore).
#
# FORJD production already uses Supabase. This script is for:
#   • forjd  — disaster-recovery restore into Supabase public
#   • partner — co-locate a partner control-plane DB into a non-public schema
#
# Required env (never echoed):
#   NEON_DATABASE_URL
#   SUPABASE_DATABASE_URL   # DIRECT: postgresql://postgres.<ref>@db.<ref>.supabase.co:5432/postgres
#
# Optional:
#   MIGRATE_MODE=partner|forjd   # default partner
#   TARGET_SCHEMA=<name>         # required for partner mode (non-public schema)
#   DUMP_DIR=./.pg_migrate_dumps
#   DRY_RUN=1
#   ALLOW_MAJOR_DOWNGRADE=0      # set 1 only after reviewing dump/restore errors
#
# Usage:
#   export NEON_DATABASE_URL='postgresql://…@….neon.tech/neondb?sslmode=require'
#   export SUPABASE_DATABASE_URL='postgresql://postgres.…@db.…supabase.co:5432/postgres'
#   DRY_RUN=1 TARGET_SCHEMA=partner_control ./scripts/pg_migrate_neon_to_supabase.sh
#   TARGET_SCHEMA=partner_control ./scripts/pg_migrate_neon_to_supabase.sh
set -euo pipefail

MIGRATE_MODE="${MIGRATE_MODE:-partner}"
TARGET_SCHEMA="${TARGET_SCHEMA:-}"
DUMP_DIR="${DUMP_DIR:-./.pg_migrate_dumps}"
DRY_RUN="${DRY_RUN:-0}"
ALLOW_MAJOR_DOWNGRADE="${ALLOW_MAJOR_DOWNGRADE:-0}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "$1 not found (install PostgreSQL client tools)"; }

need pg_dump
need pg_restore
need psql

[[ -n "${NEON_DATABASE_URL:-}" ]] || die "NEON_DATABASE_URL is required"
[[ -n "${SUPABASE_DATABASE_URL:-}" ]] || die "SUPABASE_DATABASE_URL is required"

case "${SUPABASE_DATABASE_URL}" in
  *:6543/*|*pooler.supabase.com*)
    die "Use Supabase DIRECT URI db.<ref>.supabase.co:5432 (not transaction pooler :6543)"
    ;;
esac

mkdir -p "${DUMP_DIR}"
DUMP_FILE="${DUMP_DIR}/neon_${MIGRATE_MODE}_${STAMP}.dump"
LOG_FILE="${DUMP_DIR}/migrate_${MIGRATE_MODE}_${STAMP}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "=== Neon → Supabase migration ==="
echo "mode=${MIGRATE_MODE} target_schema=${TARGET_SCHEMA:-"(n/a)"} dry_run=${DRY_RUN}"
echo "dump=${DUMP_FILE}"
echo "URLs configured (not printed)"

src_ver="$(psql "${NEON_DATABASE_URL}" -v ON_ERROR_STOP=1 -Atc "SHOW server_version_num")"
dst_ver="$(psql "${SUPABASE_DATABASE_URL}" -v ON_ERROR_STOP=1 -Atc "SHOW server_version_num")"
src_major=$((src_ver / 10000))
dst_major=$((dst_ver / 10000))
echo "source_major=${src_major} target_major=${dst_major}"

if (( src_major > dst_major )) && [[ "${ALLOW_MAJOR_DOWNGRADE}" != "1" ]]; then
  die "Source PG ${src_major} → Supabase PG ${dst_major} is a major downgrade. \
Prefer partner dumpdata/loaddata, or upgrade Supabase to PG ${src_major}. \
Override with ALLOW_MAJOR_DOWNGRADE=1 only after a dry-run restore test."
fi

echo "Ensuring Supabase extensions (idempotent)..."
psql "${SUPABASE_DATABASE_URL}" -v ON_ERROR_STOP=0 <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
SQL
# Confirm required extensions exist
psql "${SUPABASE_DATABASE_URL}" -v ON_ERROR_STOP=1 -Atc \
  "SELECT extname FROM pg_extension WHERE extname IN ('pgcrypto','vector') ORDER BY 1;"

echo "Dumping Neon public schema (custom format)..."
pg_dump "${NEON_DATABASE_URL}" \
  --format=custom \
  --no-owner \
  --no-acl \
  --verbose \
  --schema=public \
  --file="${DUMP_FILE}"

echo "Dump TOC summary:"
pg_restore --list "${DUMP_FILE}" | awk '/TABLE DATA|TABLE /{print}' | head -40

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "DRY_RUN=1 — dump finished; restore skipped."
  exit 0
fi

case "${MIGRATE_MODE}" in
  forjd)
    echo "Restoring into Supabase public (FORJD disaster-recovery path)..."
    pg_restore \
      --dbname="${SUPABASE_DATABASE_URL}" \
      --no-owner \
      --no-acl \
      --verbose \
      --single-transaction \
      "${DUMP_FILE}" || {
        echo "pg_restore reported errors — inspect ${LOG_FILE}"
        exit 1
      }
    ;;

  partner)
    [[ -n "${TARGET_SCHEMA}" ]] || die "TARGET_SCHEMA is required for partner mode"
    [[ "${TARGET_SCHEMA}" != "public" ]] || die "TARGET_SCHEMA must not be public"
    # Schema-isolate partner tables so FORJD public.* stays untouched.
    if ! command -v docker >/dev/null; then
      die "docker is required for partner mode (staging rename public→${TARGET_SCHEMA})"
    fi

    STAGE_NAME="forjd_neon_stage_${STAMP}"
    STAGE_PORT="${STAGE_PORT:-55432}"
    echo "Starting local staging Postgres on :${STAGE_PORT}..."
    docker rm -f "${STAGE_NAME}" >/dev/null 2>&1 || true
    docker run -d --name "${STAGE_NAME}" \
      -e POSTGRES_PASSWORD=stage \
      -e POSTGRES_DB=stage \
      -p "${STAGE_PORT}:5432" \
      postgres:17-alpine >/dev/null

    cleanup() {
      docker rm -f "${STAGE_NAME}" >/dev/null 2>&1 || true
    }
    trap cleanup EXIT

    echo "Waiting for staging Postgres..."
    for _ in $(seq 1 30); do
      if docker exec "${STAGE_NAME}" pg_isready -U postgres >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done

    STAGE_URL="postgresql://postgres:stage@127.0.0.1:${STAGE_PORT}/stage"
    echo "Restoring dump into staging..."
    pg_restore \
      --dbname="${STAGE_URL}" \
      --no-owner \
      --no-acl \
      --verbose \
      "${DUMP_FILE}" || true

    echo "Renaming public → ${TARGET_SCHEMA} on staging..."
    psql "${STAGE_URL}" -v ON_ERROR_STOP=1 <<SQL
ALTER SCHEMA public RENAME TO ${TARGET_SCHEMA};
CREATE SCHEMA public;
SQL

    PARTNER_DUMP="${DUMP_DIR}/partner_schema_${STAMP}.dump"
    echo "Dumping schema ${TARGET_SCHEMA} from staging..."
    pg_dump "${STAGE_URL}" \
      --format=custom \
      --no-owner \
      --no-acl \
      --schema="${TARGET_SCHEMA}" \
      --file="${PARTNER_DUMP}"

    echo "Creating ${TARGET_SCHEMA} on Supabase and restoring..."
    psql "${SUPABASE_DATABASE_URL}" -v ON_ERROR_STOP=1 \
      -c "CREATE SCHEMA IF NOT EXISTS ${TARGET_SCHEMA};"

    pg_restore \
      --dbname="${SUPABASE_DATABASE_URL}" \
      --no-owner \
      --no-acl \
      --verbose \
      --single-transaction \
      "${PARTNER_DUMP}" || {
        echo "pg_restore into ${TARGET_SCHEMA} reported errors — inspect ${LOG_FILE}"
        exit 1
      }

    echo "Grants on ${TARGET_SCHEMA}..."
    psql "${SUPABASE_DATABASE_URL}" -v ON_ERROR_STOP=0 <<SQL || true
GRANT USAGE ON SCHEMA ${TARGET_SCHEMA} TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA ${TARGET_SCHEMA} TO postgres, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA ${TARGET_SCHEMA} TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA ${TARGET_SCHEMA}
  GRANT ALL ON TABLES TO postgres, service_role;
SQL
    ;;

  *)
    die "MIGRATE_MODE must be partner or forjd"
    ;;
esac

echo
echo "=== Migration finished ==="
echo "Next steps:"
echo "  1) FORJD gates:  POSTGRES_DSN=<supabase> python backend/scripts/verify_supabase_post_migration.py"
echo "  2) Partner app: set DATABASE_URL + search_path to include ${TARGET_SCHEMA:-public}"
echo "  3) Cut traffic; keep source DB read-only ≥ 7 days before delete"
echo "  4) Rollback: point DSNs back to the source host (see docs/NEON_TO_SUPABASE.md)"
