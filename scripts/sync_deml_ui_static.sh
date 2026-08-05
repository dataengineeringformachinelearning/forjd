#!/usr/bin/env bash
# Vendor deml-ui CSS into FORJD backend/static for backend.forjd.co HTML shells.
# Prefer sibling deml-ui dist, then deml/node_modules/deml-ui, then DEML_UI_DIST.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST_DIR="$ROOT/backend/static"
SIBLING_UI="${FORJD_DEML_UI_ROOT:-$ROOT/../deml-ui}/dist/styles/deml-ui.css"
DEML_PKG="${FORJD_DEML_ROOT:-$ROOT/../deml}/node_modules/deml-ui/dist/styles/deml-ui.css"
TOKENS_SIBLING="$(dirname "$SIBLING_UI")/tokens.css"
TOKENS_DEML="$(dirname "$DEML_PKG")/tokens.css"

SRC_CSS="${DEML_UI_DIST:-}"
SRC_TOKENS="${DEML_UI_TOKENS:-}"

if [[ -z "$SRC_CSS" ]]; then
  if [[ -f "$SIBLING_UI" ]]; then
    SRC_CSS="$SIBLING_UI"
    SRC_TOKENS="${SRC_TOKENS:-$TOKENS_SIBLING}"
  elif [[ -f "$DEML_PKG" ]]; then
    SRC_CSS="$DEML_PKG"
    SRC_TOKENS="${SRC_TOKENS:-$TOKENS_DEML}"
  else
    echo "deml-ui.css not found. Build sibling deml-ui or install deml-ui in deml/." >&2
    echo "  Looked: $SIBLING_UI" >&2
    echo "  Looked: $DEML_PKG" >&2
    exit 1
  fi
fi

mkdir -p "$DEST_DIR"
cp "$SRC_CSS" "$DEST_DIR/deml-ui.css"
if [[ -n "${SRC_TOKENS}" && -f "$SRC_TOKENS" ]]; then
  cp "$SRC_TOKENS" "$DEST_DIR/deml-ui-tokens.css"
fi

echo "Synced deml-ui static → $DEST_DIR (from $SRC_CSS)"
