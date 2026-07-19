#!/usr/bin/env bash
# Remint a tenant fjsvc_ token after sql/017–019 scope changes.
#
# Usage:
#   export FORJD_API_URL=https://backend.forjd.co
#   export FORJD_HUMAN_JWT='eyJ…'          # human owner/admin JWT
#   export FORJD_TENANT_ID='uuid'
#   ./scripts/remint_service_account.sh [name]
#
# Prints the new token once. Store only in partner secrets (Fly env:FORJD_SERVICE_TOKEN).
# Then revoke the old service account id if rotating.
#
# Includes tenants:erase explicitly (not in DEFAULT_SCOPES) for partner
# account-deletion sagas. Omit erase by setting FORJD_INCLUDE_ERASE=0.

set -euo pipefail

API="${FORJD_API_URL:?set FORJD_API_URL}"
JWT="${FORJD_HUMAN_JWT:?set FORJD_HUMAN_JWT (human owner/admin)}"
TENANT="${FORJD_TENANT_ID:?set FORJD_TENANT_ID}"
NAME="${1:-partner-$(date +%Y%m%d)}"
INCLUDE_ERASE="${FORJD_INCLUDE_ERASE:-1}"

SCOPES='[
  "ingest:write","ingest:read",
  "projections:read","projections:run",
  "sessions:write","sessions:read",
  "replay:read","replay:write",
  "status:read","status:write",
  "analytics:read",
  "exports:read","exports:write",
  "vulnerabilities:read","vulnerabilities:write",
  "integrations:write"
]'
if [[ "${INCLUDE_ERASE}" == "1" ]]; then
  SCOPES='[
  "ingest:write","ingest:read",
  "projections:read","projections:run",
  "sessions:write","sessions:read",
  "replay:read","replay:write",
  "status:read","status:write",
  "analytics:read",
  "exports:read","exports:write",
  "vulnerabilities:read","vulnerabilities:write",
  "integrations:write",
  "tenants:erase"
]'
fi

echo "Minting service account name=${NAME} tenant=${TENANT} include_erase=${INCLUDE_ERASE} …" >&2
curl -fsS -X POST "${API}/api/v1/service-accounts" \
  -H "Authorization: Bearer ${JWT}" \
  -H "Content-Type: application/json" \
  -d "{\"tenant_id\":\"${TENANT}\",\"name\":\"${NAME}\",\"subprocessor\":\"partner\",\"scopes\":${SCOPES}}" \
  | tee /dev/stderr
echo >&2
echo "Copy token.plain once into partner secrets; never commit." >&2
