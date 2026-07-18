#!/usr/bin/env bash
# Apply backend/sql/003–016 inside forjd-backend (uses machine POSTGRES_DSN; never prints it).
#
# Usage:
#   ./scripts/apply_sql_on_fly.sh
#
# The Python applicator lives in the deployed image after `fly deploy --config fly.api.toml`.
# For a one-shot before redeploy, this uploads the script via stdin to python -c is fragile;
# prefer redeploy first, then run this.
set -euo pipefail

APP="${APP:-forjd-backend}"

# Prefer the image-bundled script (present after backend deploy that includes scripts/).
fly ssh console -a "${APP}" -C 'sh -c "cd /app && .venv/bin/python scripts/apply_sql_migrations.py"'
