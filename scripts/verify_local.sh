#!/usr/bin/env bash
# Prove the local API is up (docs/START_HERE.md). Requires npm run dev:api.
set -euo pipefail

BASE="${FORJD_API_BASE:-http://127.0.0.1:8000}"
fail=0

check() {
  local path="$1"
  local label="$2"
  local url="${BASE}${path}"
  local body
  if ! body="$(curl -fsS --max-time 5 "$url" 2>/dev/null)"; then
    echo "✗ ${label}  ${url}  (not reachable — is npm run dev:api running?)"
    fail=1
    return
  fi
  echo "✓ ${label}  ${url}"
  echo "  ${body}" | head -c 200
  echo ""
}

echo "FORJD verify — ${BASE}"
echo ""
check "/health" "health"
check "/ready" "ready"
check "/api/v1/capabilities" "capabilities"

if [[ "$fail" -ne 0 ]]; then
  echo ""
  echo "Fix:"
  echo "  1. npm run bootstrap   # once"
  echo "  2. npm run dev:api     # leave running"
  echo "  3. npm run verify"
  echo "See docs/START_HERE.md"
  exit 1
fi

echo ""
echo "✓ Local API looks healthy. Splash/docs: ${BASE}/  ·  ${BASE}/docs"
