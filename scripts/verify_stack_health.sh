#!/usr/bin/env bash
# Runtime verification for FORJD (+ optional DEML soft-wiring).
# Usage:
#   ./scripts/verify_stack_health.sh
#   FORJD_API=https://backend.forjd.co DEML_API=https://backend.deml.app ./scripts/verify_stack_health.sh
set -euo pipefail

FORJD_API="${FORJD_API:-https://backend.forjd.co}"
DEML_API="${DEML_API:-https://backend.deml.app}"

pass=0
fail=0

check_json() {
  local name="$1"
  local url="$2"
  local jq_expr="$3"
  local body code
  body="$(mktemp)"
  code="$(curl -sS -o "$body" -w '%{http_code}' --max-time 8 -H 'Accept: application/json' "$url" || true)"
  if [[ "$code" != "200" ]]; then
    echo "FAIL  $name  HTTP $code  $url"
    cat "$body" || true
    echo
    fail=$((fail + 1))
    rm -f "$body"
    return
  fi
  if ! jq -e "$jq_expr" "$body" >/dev/null 2>&1; then
    echo "FAIL  $name  contract  $jq_expr"
    cat "$body"
    echo
    fail=$((fail + 1))
    rm -f "$body"
    return
  fi
  echo "OK    $name"
  pass=$((pass + 1))
  rm -f "$body"
}

echo "== FORJD =="
check_json "FORJD /health" \
  "${FORJD_API}/health" \
  '.status == "healthy"'

check_json "FORJD /ready" \
  "${FORJD_API}/ready" \
  '.status == "ready" and .checks.postgres == true and .checks.redis == true'

# Engine block is informational; warn when present but not ok.
engine_body="$(mktemp)"
if curl -sS --max-time 8 -H 'Accept: application/json' "${FORJD_API}/ready" -o "$engine_body"; then
  if jq -e '.engine != null and .engine.ok != true' "$engine_body" >/dev/null 2>&1; then
    echo "WARN  FORJD engine probe not ok (API still ready — soft dependency)"
  elif jq -e '.engine.ok == true' "$engine_body" >/dev/null 2>&1; then
    echo "OK    FORJD engine probe"
    pass=$((pass + 1))
  else
    echo "SKIP  FORJD engine block absent (PyO3-only or unconfigured ENGINE_URL)"
  fi
fi
rm -f "$engine_body"

echo
echo "== DEML soft wiring (optional) =="
deml_ready="$(mktemp)"
if curl -sS --max-time 8 -H 'Accept: application/json' "${DEML_API}/api/v1/ready" -o "$deml_ready"; then
  if jq -e '.status == "ready" and (.forjd_health | type == "string")' "$deml_ready" >/dev/null 2>&1; then
    echo "OK    DEML /ready exposes forjd_health"
    pass=$((pass + 1))
  else
    echo "WARN  DEML /ready missing forjd_health/mode — deploy DEML reliability branch (soft wiring)"
  fi
else
  echo "SKIP  DEML /ready unreachable"
fi
rm -f "$deml_ready"

echo
echo "Passed: $pass  Failed: $fail"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
