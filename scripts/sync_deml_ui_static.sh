#!/usr/bin/env bash
# Vendor deml-ui CSS into FORJD backend/static for backend.forjd.co HTML shells.
# Prefer sibling deml-ui dist, then deml/node_modules/deml-ui, then DEML_UI_DIST.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST_DIR="$ROOT/backend/static"
SIBLING_UI="${FORJD_DEML_UI_ROOT:-$ROOT/../deml-ui}/dist/styles/deml-ui.css"
DEML_PKG="${FORJD_DEML_ROOT:-$ROOT/../deml}/node_modules/deml-ui/dist/styles/deml-ui.css"

SRC_CSS="${DEML_UI_DIST:-}"

if [[ -z "$SRC_CSS" ]]; then
  if [[ -f "$SIBLING_UI" ]]; then
    SRC_CSS="$SIBLING_UI"
  elif [[ -f "$DEML_PKG" ]]; then
    SRC_CSS="$DEML_PKG"
  else
    echo "deml-ui.css not found. Build sibling deml-ui or install deml-ui in deml/." >&2
    echo "  Looked: $SIBLING_UI" >&2
    echo "  Looked: $DEML_PKG" >&2
    exit 1
  fi
fi

mkdir -p "$DEST_DIR"
cp "$SRC_CSS" "$DEST_DIR/deml-ui.css"

echo "Synced deml-ui static → $DEST_DIR (from $SRC_CSS)"
