#!/usr/bin/env bash
# Bootstrap a local FORJD stack for new developers (docs/START_HERE.md).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SKIP_DOCKER=0
FRONTEND_ONLY=0
NO_HOOKS=0

for arg in "$@"; do
  case "$arg" in
    --skip-docker) SKIP_DOCKER=1 ;;
    --frontend-only) FRONTEND_ONLY=1 ;;
    --no-hooks) NO_HOOKS=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/bootstrap_local.sh [--frontend-only] [--skip-docker] [--no-hooks]

  Default: env file, Docker Postgres+Dragonfly, uv sync, frontend npm install, hooks.
  --frontend-only  Skip Docker + backend uv sync (landing only).
  --skip-docker    Assume Postgres :5432 and Redis/Dragonfly :6379 already run.
  --no-hooks       Skip npm run install-hooks.

See docs/START_HERE.md.
EOF
      exit 0
      ;;
    *)
      echo "✗ Unknown flag: $arg (try --help)" >&2
      exit 2
      ;;
  esac
done

# --- Pretty steps ---
step() { echo ""; echo "→ $*"; }
ok() { echo "  ✓ $*"; }
warn() { echo "  ! $*" >&2; }
die() { echo "✗ $*" >&2; exit 1; }

# --- Prerequisite checks ---
step "Checking prerequisites"
command -v python3 >/dev/null || die "python3 required"
if [[ "$FRONTEND_ONLY" -eq 0 ]]; then
  command -v uv >/dev/null || die "uv required — https://docs.astral.sh/uv/"
  command -v rustc >/dev/null || die "rustc required — https://rustup.rs/ (pin 1.97)"
  command -v cargo >/dev/null || die "cargo required — install via rustup"
fi
command -v node >/dev/null || die "node required — see frontend/.nvmrc (Node 24)"
command -v npm >/dev/null || die "npm required"

NODE_VER="$(node -v | sed 's/^v//')"
NODE_MAJOR="${NODE_VER%%.*}"
NODE_MINOR="$(echo "$NODE_VER" | cut -d. -f2)"
NODE_OK=0
if [[ "$NODE_MAJOR" -gt 24 ]]; then NODE_OK=1; fi
if [[ "$NODE_MAJOR" -eq 24 && "$NODE_MINOR" -ge 15 ]]; then NODE_OK=1; fi
if [[ "$NODE_MAJOR" -eq 22 && "$NODE_MINOR" -ge 22 ]]; then NODE_OK=1; fi
[[ "$NODE_OK" -eq 1 ]] || die "Node $NODE_VER too old — need ^22.22.3 or ^24.15+ (nvm use)"
ok "Node v$NODE_VER"

if [[ "$FRONTEND_ONLY" -eq 0 ]]; then
  RUST_VER="$(rustc --version 2>/dev/null || true)"
  RUST_PIN="$(sed -n 's/^channel = "\\([^"]*\\)"/\\1/p' engine/rust-toolchain.toml | head -n 1)"
  RUST_PIN="${RUST_PIN:-1.97.1}"
  if [[ "$RUST_VER" != "rustc $RUST_PIN "* ]]; then
    command -v rustup >/dev/null || die "rustc is not $RUST_PIN and rustup is unavailable"
    PINNED_RUSTC="$(rustup which rustc --toolchain "$RUST_PIN" 2>/dev/null)" ||
      die "Install the pinned toolchain: rustup install $RUST_PIN"
    PINNED_CARGO="$(rustup which cargo --toolchain "$RUST_PIN" 2>/dev/null)" ||
      die "Install the pinned toolchain: rustup install $RUST_PIN"
    export RUSTC="$PINNED_RUSTC"
    export CARGO="$PINNED_CARGO"
    export PATH="$(dirname "$PINNED_CARGO"):$PATH"
    ok "Using pinned rustc $RUST_PIN via rustup (PATH had $RUST_VER)"
  else
    ok "$RUST_VER"
  fi
fi

if [[ "$SKIP_DOCKER" -eq 0 && "$FRONTEND_ONLY" -eq 0 ]]; then
  command -v docker >/dev/null || die "docker required (or pass --skip-docker)"
  docker info >/dev/null 2>&1 || die "Docker daemon not running — start Docker Desktop"
  ok "Docker daemon"
fi

# --- Env ---
step "Backend env"
if [[ ! -f backend/.env ]]; then
  cp backend/.env.example backend/.env
  ok "Created backend/.env from .env.example (local Postgres + soft-migrate)"
else
  ok "backend/.env already present"
fi

# --- Docker: Postgres + Dragonfly only (skip Prefect — binds :4200) ---
if [[ "$SKIP_DOCKER" -eq 0 && "$FRONTEND_ONLY" -eq 0 ]]; then
  step "Starting Dragonfly + Postgres (local-db profile)"
  (
    cd backend
    docker compose --profile local-db up -d dragonfly postgres
  )
  ok "Waiting for Postgres readiness…"
  for _ in $(seq 1 30); do
    if docker compose -f backend/docker-compose.yml --profile local-db exec -T postgres \
      pg_isready -U postgres -d forjd >/dev/null 2>&1; then
      ok "Postgres ready on :5432"
      break
    fi
    sleep 1
  done
  ok "Dragonfly on :6379 (password forjd-dev-local)"
fi

# --- Backend deps (includes Rust engine wheel) ---
if [[ "$FRONTEND_ONLY" -eq 0 ]]; then
  step "uv sync --locked (first run builds the Rust engine — often 5–15 min)"
  (
    cd backend
    uv sync --locked
  )
  ok "Backend + engine wheel ready"
fi

# --- Frontend ---
step "Frontend npm install"
(
  cd frontend
  npm install
)
ok "frontend/node_modules ready"

# --- Hooks ---
if [[ "$NO_HOOKS" -eq 0 ]]; then
  step "Git hooks"
  if command -v uvx >/dev/null 2>&1; then
    bash scripts/install_hooks.sh
  else
    warn "uvx missing — skip hooks; later: npm run install-hooks"
  fi
fi

# --- Doctor (non-fatal soft warnings) ---
step "Doctor"
python3 scripts/forjd_tooling.py doctor || true

cat <<'EOF'

✓ Bootstrap finished.

Next (two terminals):
  npm run dev:api     # http://127.0.0.1:8000
  npm run dev:web     # http://127.0.0.1:4200

Then prove it:
  npm run verify

Guide: docs/START_HERE.md
EOF
