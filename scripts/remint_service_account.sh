#!/usr/bin/env bash
# Remint a tenant fjsvc_ token using the API's canonical default scopes.
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
# tenants:erase is excluded by default. Opt in only for account-deletion sagas:
#   FORJD_INCLUDE_ERASE=1 ./scripts/remint_service_account.sh [name]

set -euo pipefail

API="${FORJD_API_URL:?set FORJD_API_URL}"
API="${API%/}"
JWT="${FORJD_HUMAN_JWT:?set FORJD_HUMAN_JWT (human owner/admin)}"
TENANT="${FORJD_TENANT_ID:?set FORJD_TENANT_ID}"
NAME="${1:-partner-$(date +%Y%m%d)}"
INCLUDE_ERASE="${FORJD_INCLUDE_ERASE:-0}"

case "${INCLUDE_ERASE}" in
  1|true|TRUE|yes|YES) INCLUDE_ERASE_JSON=true ;;
  0|false|FALSE|no|NO) INCLUDE_ERASE_JSON=false ;;
  *)
    echo "FORJD_INCLUDE_ERASE must be 0/1, false/true, or no/yes" >&2
    exit 2
    ;;
esac

# Python is already required by the FORJD backend and safely JSON-escapes names.
# Deliberately omit scopes: the backend owns DEFAULT_SCOPES as the single source.
PAYLOAD="$(
  python3 -c 'import json, sys; print(json.dumps({"tenant_id": sys.argv[1], "name": sys.argv[2], "subprocessor": "partner", "include_tenant_erase": sys.argv[3] == "true"}, separators=(",", ":")))' \
    "${TENANT}" "${NAME}" "${INCLUDE_ERASE_JSON}"
)"

echo "Minting service account name=${NAME} tenant=${TENANT} canonical_defaults=true include_tenant_erase=${INCLUDE_ERASE_JSON} …" >&2
curl -fsS -X POST "${API}/api/v1/service-accounts" \
  -H "Authorization: Bearer ${JWT}" \
  -H "Content-Type: application/json" \
  --data-binary "${PAYLOAD}"
printf '\n'
echo "Copy service_account.token once into partner secrets; never commit." >&2
