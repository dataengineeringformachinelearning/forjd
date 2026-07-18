#!/usr/bin/env bash
# Copy Postgres + Dragonfly DSNs from forjd-backend → forjd-engine (no stdout of values).
# Then enable the full data plane (FORJD_ROLE=all).
#
# Usage (from repo root, flyctl logged in):
#   ./scripts/sync_engine_dataplane_secrets.sh
set -euo pipefail

BACKEND_APP="${BACKEND_APP:-forjd-backend}"
ENGINE_APP="${ENGINE_APP:-forjd-engine}"

echo "Reading DSNs from ${BACKEND_APP} (values not printed)..."
POSTGRES_DSN="$(
  fly ssh console -a "${BACKEND_APP}" -C 'printenv POSTGRES_DSN' 2>/dev/null \
    | tr -d '\r' \
    | sed -n '/^postgres/p;/^postgresql/p' \
    | tail -n1
)"
REDIS_URL="$(
  fly ssh console -a "${BACKEND_APP}" -C 'printenv REDIS_URL' 2>/dev/null \
    | tr -d '\r' \
    | sed -n '/^redis/p;/^rediss/p' \
    | tail -n1
)"

if [[ -z "${POSTGRES_DSN}" || -z "${REDIS_URL}" ]]; then
  echo "Failed to read POSTGRES_DSN / REDIS_URL from ${BACKEND_APP}" >&2
  exit 1
fi

echo "Setting DATABASE_URL, POSTGRES_DSN, REDIS_URL, FORJD_ROLE=all on ${ENGINE_APP}..."
fly secrets set \
  "DATABASE_URL=${POSTGRES_DSN}" \
  "POSTGRES_DSN=${POSTGRES_DSN}" \
  "REDIS_URL=${REDIS_URL}" \
  "FORJD_ROLE=all" \
  -a "${ENGINE_APP}"

echo "Done. Verify with: curl -sS https://${ENGINE_APP}.fly.dev/ready"
