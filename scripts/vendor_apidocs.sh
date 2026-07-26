#!/usr/bin/env bash
# Pin and download self-hosted Swagger UI + ReDoc into backend/static/vendor/.
# Durable alternative to jsDelivr CDN (docs/SUITE_UI_UNIFICATION_COMPLETION.md G1).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SWAGGER_VER="${FORJD_SWAGGER_UI_VERSION:-5.18.3}"
REDOC_VER="${FORJD_REDOC_VERSION:-2.5.0}"
BASE_SWAGGER="https://cdn.jsdelivr.net/npm/swagger-ui-dist@${SWAGGER_VER}"
BASE_REDOC="https://cdn.jsdelivr.net/npm/redoc@${REDOC_VER}"

SWAGGER_DIR="$ROOT/backend/static/vendor/swagger-ui-dist"
REDOC_DIR="$ROOT/backend/static/vendor/redoc"

mkdir -p "$SWAGGER_DIR" "$REDOC_DIR"

echo "→ swagger-ui-dist@${SWAGGER_VER}"
curl -fsSL "$BASE_SWAGGER/swagger-ui.css" -o "$SWAGGER_DIR/swagger-ui.css"
curl -fsSL "$BASE_SWAGGER/swagger-ui-bundle.js" -o "$SWAGGER_DIR/swagger-ui-bundle.js"
curl -fsSL "$BASE_SWAGGER/swagger-ui.css.map" -o "$SWAGGER_DIR/swagger-ui.css.map" || true
printf '%s\n' "$SWAGGER_VER" >"$SWAGGER_DIR/VERSION"

echo "→ redoc@${REDOC_VER}"
curl -fsSL "$BASE_REDOC/bundles/redoc.standalone.js" -o "$REDOC_DIR/redoc.standalone.js"
printf '%s\n' "$REDOC_VER" >"$REDOC_DIR/VERSION"

echo "✓ Vendored under backend/static/vendor/ (commit these files)."
