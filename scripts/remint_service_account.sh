#!/usr/bin/env bash
# Remint a tenant fjsvc_ token after sql/017–018 scope expansion.
#
# Usage:
#   export FORJD_API_URL=https://backend.forjd.co
#   export FORJD_HUMAN_JWT='eyJ…'          # human owner/admin JWT
#   export FORJD_TENANT_ID='uuid'
#   ./scripts/remint_service_account.sh [name]
#
# Prints the new token once. Store only in partner secrets (Fly/Railway env:FORJD_SERVICE_TOKEN).
# Then revoke the old service account id if rotating.

set -euo pipefail

API="${FORJD_API_URL:?set FORJD_API_URL}"
JWT="${FORJD_HUMAN_JWT:?set FORJD_HUMAN_JWT (human owner/admin)}"
TENANT="${FORJD_TENANT_ID:?set FORJD_TENANT_ID}"
NAME="${1:-partner-cutover-$(date +%Y%m%d)}"

echo "Minting service account name=${NAME} tenant=${TENANT} …" >&2
curl -fsS -X POST "${API}/api/v1/service-accounts" \
  -H "Authorization: Bearer ${JWT}" \
  -H "Content-Type: application/json" \
  -d "{\"tenant_id\":\"${TENANT}\",\"name\":\"${NAME}\",\"subprocessor\":\"partner\"}" \
  | tee /dev/stderr
echo >&2
echo "Copy token.plain once into partner secrets; never commit." >&2
