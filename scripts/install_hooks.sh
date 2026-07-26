#!/usr/bin/env bash
# Install FORJD git hooks (pre-commit quality + commit-msg convention).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v uvx >/dev/null 2>&1; then
  echo "✗ uvx not found — install uv: https://docs.astral.sh/uv/" >&2
  exit 1
fi

echo "→ Installing pre-commit + commit-msg hooks"
uvx pre-commit install --install-hooks \
  --hook-type pre-commit \
  --hook-type commit-msg

echo ""
echo "✓ Hooks installed."
echo "  pre-commit:  whitespace, ruff, prettier, typecheck, catalog, suite purity, rustfmt"
echo "  commit-msg:  Conventional Commits (docs/GIT.md)"
echo "  Manual:      npm run quality"
echo "  All files:   uvx pre-commit run --all-files"
echo "  Msg check:   python3 scripts/check_commit_msg.py --self-test"
echo ""
