#!/usr/bin/env bash
# Copy Postgres + Dragonfly DSNs from forjd-backend → forjd-engine, mint internode
# bus keys if missing, then enable the full data plane (FORJD_ROLE=all).
#
# Usage (from repo root, flyctl logged in):
#   ./scripts/sync_engine_dataplane_secrets.sh
#
# Override / reuse keys (do not print values):
#   FORJD_INTERNODE_ACTIVE_KID=v1 FORJD_INTERNODE_KEYS='{"v1":"..."}' ./scripts/...
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

# Production data-plane requires sslmode on Postgres (FORJD_TRANSPORT_SECURITY=required).
case "${POSTGRES_DSN}" in
  *sslmode=*) ;;
  *\?*) POSTGRES_DSN="${POSTGRES_DSN}&sslmode=require" ;;
  *) POSTGRES_DSN="${POSTGRES_DSN}?sslmode=require" ;;
esac

# --- Internode AES-256-GCM keys (required for bus roles on Fly) ---
# FORJD_ROLE=all includes relay/scheduler/normalizer → needs_bus() → encryption required.
ACTIVE_KID="${FORJD_INTERNODE_ACTIVE_KID:-v1}"
if [[ -z "${FORJD_INTERNODE_KEYS:-}" ]]; then
  if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl is required to mint FORJD_INTERNODE_KEYS" >&2
    exit 1
  fi
  # 32 bytes → base64url (no padding), matching engine internode::load_keyring.
  KEY_B64URL="$(openssl rand 32 | openssl base64 -A | tr '+/' '-_' | tr -d '=')"
  FORJD_INTERNODE_KEYS="$(printf '{"%s":"%s"}' "${ACTIVE_KID}" "${KEY_B64URL}")"
  echo "Minted new FORJD_INTERNODE_KEYS (kid=${ACTIVE_KID}; value not printed)."
else
  echo "Using provided FORJD_INTERNODE_KEYS (value not printed)."
fi

echo "Setting DATABASE_URL, REDIS_URL, internode keys, FORJD_ROLE=all on ${ENGINE_APP}..."
fly secrets set \
  "DATABASE_URL=${POSTGRES_DSN}" \
  "POSTGRES_DSN=${POSTGRES_DSN}" \
  "REDIS_URL=${REDIS_URL}" \
  "FORJD_INTERNODE_ENCRYPTION=required" \
  "FORJD_INTERNODE_ACTIVE_KID=${ACTIVE_KID}" \
  "FORJD_INTERNODE_KEYS=${FORJD_INTERNODE_KEYS}" \
  "FORJD_ROLE=all" \
  -a "${ENGINE_APP}"

echo "Done. Verify with:"
echo "  fly logs -a ${ENGINE_APP}          # look for 'data plane role' All + no internode bail"
echo "  curl -sS https://${ENGINE_APP}.fly.dev/health"
echo "  curl -sS https://${ENGINE_APP}.fly.dev/ready"
echo "Rollback to process-only: fly secrets set FORJD_ROLE=engine -a ${ENGINE_APP}"
