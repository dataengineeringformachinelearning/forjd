#!/bin/sh
# Ensure volumes + home dirs are writable, then drop to the non-root app user.
set -eu
MODEL_DIR="${ML_MODEL_DIR:-/data/models}"
APP_HOME=/home/forjd

mkdir -p "$MODEL_DIR" "$APP_HOME/.prefect"
chown -R 1001:1001 "$MODEL_DIR" "$APP_HOME" 2>/dev/null || true

export HOME="$APP_HOME"
export USER=forjd
export PREFECT_HOME="$APP_HOME/.prefect"

exec setpriv --reuid=1001 --regid=1001 --init-groups -- "$@"
