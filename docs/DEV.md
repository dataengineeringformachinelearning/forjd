# FORJD local developer tooling

Short guide for reliable local loops: Node, uv/maturin, hot reload, and clear fixes.

**First clone?** Use [`START_HERE.md`](START_HERE.md) (`npm run bootstrap` → `dev:api` / `dev:web` → `verify`).

## One-command checks

From the **repo root**:

```bash
npm run bootstrap       # once — env, Docker DB, uv sync, frontend install, hooks
npm run verify          # curl /health /ready /capabilities (API must be up)
npm run install-hooks   # pre-commit + commit-msg (see docs/GIT.md)
npm run doctor          # Node / uv / Rust / .env / Docker / suite / workflows paths
npm run validate:workflows  # Workflow YAML vs schema + detector/processor registries
npm run quality         # Fast: catalog + workflows + ruff + prettier + typecheck + suite purity
npm run quality:full    # Also tests + engine fmt/clippy (CI-aligned) + frontend build
npm run format          # Auto-fix frontend prettier + backend ruff + engine rustfmt
npm run dev:api         # FastAPI + reload → http://127.0.0.1:8000
npm run dev:web         # Angular landing → http://127.0.0.1:4200
```

Equivalent: `python3 scripts/forjd_tooling.py bootstrap|doctor|verify|validate-workflows|quality|install-hooks|api|web`.

Partner/contributor extension map: [`EXTENDING.md`](EXTENDING.md).

Layer commands and CI map: [`TESTING.md`](TESTING.md). Commits / history: [`GIT.md`](GIT.md). Product briefing: [`../AGENTS.md`](../AGENTS.md).

## Lint / format / typecheck

| Layer | Local | Enforced by |
|-------|--------|-------------|
| Backend | `cd backend && uv run ruff check . && uv run ruff format --check .` | pre-commit + CI + `npm run quality` |
| Frontend format | `cd frontend && npm run format:check` | pre-commit + CI + `npm run quality` |
| Frontend types | `cd frontend && npm run typecheck` (`tsc --noEmit` app + forjd-ui) | pre-commit + CI + `npm run quality` |
| Template types | `cd frontend && npm run build` (strict Angular templates) | CI + `npm run quality:full` |
| Engine | `cd engine && cargo fmt --all -- --check && cargo clippy …` | pre-commit (fmt) + CI + `quality:full` |

No ESLint target — Prettier + TypeScript strict + Angular `strictTemplates` (via build). Fix style: `cd frontend && npm run format`.

## Commits / history

Conventional Commits + squash-merge practice: [`GIT.md`](GIT.md). The `commit-msg` hook rejects vague / non-conventional subjects after `npm run install-hooks`.

```bash
python3 scripts/check_commit_msg.py --self-test
echo 'feat(frontend): add preferences store' | python3 scripts/check_commit_msg.py
```

## Frontend (hot reload)

```bash
cd frontend
nvm use                 # reads .nvmrc → Node 24
npm install
npm run preflight       # engines + suite CSS presence
npm start               # 127.0.0.1:4200, HMR via Angular/Vite
```

| Script | Purpose |
|--------|---------|
| `npm start` / `npm run dev` | Dev server (preflight first) |
| `npm run start:poll` | Same with file polling (`FORJD_POLL=1000`) when watchers die |
| `npm run clean:cache` | Drop `.angular/cache` after stuck HMR / corrupt Vite cache |
| `npm run format` / `format:check` | Prettier write / check |
| `npm run typecheck` / `lint` | `tsc --noEmit` (app + forjd-ui); lint = format:check + typecheck |
| `npm run sync:suite` | Vendor suite CSS from DEML (`FORJD_DEML_ROOT` override) |
| `npm run suite:purity` | Hash lockstep forjd-ui ↔ backend/static |

### Hot reload reliability

1. **EMFILE / “too many open files”** — raise limits, then use polling:
   ```bash
   ulimit -n 10240
   cd frontend && npm run start:poll
   ```
2. **Stale or blank page after pull** — `npm run clean:cache && npm start`.
3. **Wrong Node** — Angular 22 CLI needs ≥ 22.22.3. Cursor Cloud: put nvm Node 24 ahead of `/exec-daemon` on `PATH` (see `AGENTS.md`).
4. **API badge “not ready”** — start backend (`npm run dev:api`); landing probes `http://127.0.0.1:8000/ready`.

Serve binds **127.0.0.1:4200** (not all interfaces) for predictable Playwright and CORS.

## Backend (reload)

```bash
cd backend
cp .env.example .env    # once
uv sync --locked        # builds ../engine via maturin
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --reload-dir app
# or: npm run dev:api from repo root
```

`uv run forjd` also respects `DEBUG` for reload. Prefer `--reload-dir app` so `.venv` / engine rebuilds do not thrash the watcher.

### Common `uv sync` failures

| Symptom | Fix |
|---------|-----|
| Rust / maturin version mismatch | `rustup show` → install **1.97** per `engine/rust-toolchain.toml` |
| PyO3 link errors after engine edits | `cd backend && uv sync` again |
| Python 3.14 selected | Backend pins 3.12 — `uv` should pick it; check `requires-python` |

## Suite sync (DEML)

Canonical tokens live in the DEML sibling. Default path:

`../dataengineeringformachinelearning/packages/viking-ui/src/tokens`

```bash
export FORJD_DEML_ROOT=/absolute/path/to/dataengineeringformachinelearning
cd frontend && npm run sync:suite && npm run suite:purity
```

Sync failures print the expected path and clone/override hints (not a bare “Missing …”).

## Playwright e2e

```bash
cd frontend
npm run test:e2e:install   # once per machine
npm run test:e2e
```

CI installs Chromium with OS deps; locally `test:e2e:install` is enough on macOS.

## Backing services

Postgres + Dragonfly must be up before `/ready` is green. Prefer:

```bash
cd backend && docker compose --profile local-db up -d dragonfly postgres
```

(`npm run bootstrap` does this.) Do **not** start Compose `prefect-server` while using the Angular landing — both want port **4200**. Native Postgres/Redis on Cursor Cloud VMs do not auto-start each session.
