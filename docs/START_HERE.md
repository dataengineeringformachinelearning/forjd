# Start here (≈10 minutes)

New to FORJD? This page is the short path: understand the system, bootstrap a local stack, and prove it runs.

> **Cold vs warm:** Your *attention* stays under ~10 minutes (copy/paste + two terminals). The first `uv sync` builds the Rust engine and may wait 5–15 minutes on a quiet machine — leave it running. Later days restart in under two minutes.

## What FORJD is

FORJD is a **universal secure streaming engine**. Partners send **sealed (E2EE) events** with a tenant-bound `fjsvc_` token. FORJD stores ciphertext, runs metadata-only pipelines, and exposes projections/analytics — not a browser product console.

```text
Partner SaaS ──fjsvc_──► FastAPI (backend/) ──► Rust engine (engine/)
                              │                      │
                              ▼                      ▼
                     Postgres (Supabase/local)   Dragonfly streams
                              │
                              ▼
                     Static landing (frontend/) — docs + chrome only
```

| Folder | Role |
|--------|------|
| `backend/` | FastAPI control plane, Prefect, Polars, SQL |
| `engine/` | Rust sealed pipeline + data plane |
| `frontend/` | Angular landing + `forjd-ui` suite adapter |
| `docs/` | How we work (this file, DEV, GIT, TESTING, …) |
| `AGENTS.md` / `ARCHITECTURE.md` | Product briefing + architecture contract |

There is **no operational UI** in the landing — partners integrate via API + YAML workflows.

## Prerequisites (once per machine)

| Tool | Notes |
|------|--------|
| [uv](https://docs.astral.sh/uv/) | Backend + builds engine |
| Rust **1.97** via [rustup](https://rustup.rs/) | `rustup install 1.97` (see `engine/rust-toolchain.toml`) |
| Node **24** (or ≥22.22.3) | `frontend/.nvmrc` — `nvm use` |
| Docker Desktop (or Engine) | Local Postgres + Dragonfly |

Optional later: Supabase project, flyctl, DEML sibling for suite CSS sync.

## Bootstrap (one command)

From the **repo root**:

```bash
npm run bootstrap
```

That script will:

1. Check `uv` / Node / Docker / Rust
2. Copy `backend/.env.example` → `backend/.env` if missing (local Postgres DSN + `SOFT_MIGRATE_SCHEMA=true`)
3. Start **Dragonfly** + **Postgres** (`docker compose --profile local-db`) — not Prefect (port 4200 clashes with the Angular landing)
4. `uv sync --locked` in `backend/` (builds the engine wheel)
5. `npm install` in `frontend/`
6. Install git hooks (`pre-commit` + commit-msg)

Flags:

```bash
npm run bootstrap -- --skip-docker    # you already run Postgres/Redis yourself
npm run bootstrap -- --frontend-only  # landing only (no API / uv sync)
npm run bootstrap -- --no-hooks       # skip git hook install
```

Then:

```bash
npm run doctor          # toolchain sanity
```

## Run (two terminals)

```bash
# Terminal A — API (reload)
npm run dev:api
# → http://127.0.0.1:8000/health  ·  /ready  ·  /api/v1/capabilities

# Terminal B — landing
npm run dev:web
# → http://127.0.0.1:4200
```

Prove it:

```bash
npm run verify          # curls health + ready + capabilities (API must be up)
```

| Check | Expect |
|-------|--------|
| `GET /health` | process up |
| `GET /ready` | Postgres + Dragonfly reachable (soft-migrate shapes tables locally) |
| Landing | brand + docs links; API badge turns ready when `/ready` is green |

## Mental shortcuts

- **Local DB** uses soft-migrate (table shapes). Production applies SQL `003`–`029` on Supabase — see [`backend/sql/README.md`](../backend/sql/README.md).
- **Engine:** empty `ENGINE_URL` → in-process PyO3 wheel from `uv sync`. Compose `forjd-engine` is optional.
- **Auth for partners:** tenant `fjsvc_` tokens — never Firebase / end-user tokens at the FORJD edge ([`backend/docs/AUTH.md`](../backend/docs/AUTH.md)).
- **Commits:** Conventional Commits ([`GIT.md`](GIT.md)).
- **Quality:** `npm run quality` before a PR ([`DEV.md`](DEV.md)).

## If something fails

| Symptom | Fix |
|---------|-----|
| Doctor: missing `uv` / Node / cargo | Install tools above; re-run `npm run doctor` |
| `uv sync` Rust/maturin errors | `rustup install 1.97 && cd engine && rustup override set 1.97` |
| `/ready` not ready | `cd backend && docker compose --profile local-db up -d dragonfly postgres` |
| Port 4200 busy | Stop Prefect UI or anything else on 4200; landing owns that port locally |
| Angular Node version error | `nvm use` (Node 24) — see `AGENTS.md` Cursor Cloud note |
| Suite sync / DEML missing | Optional for day-1; vendored CSS already ships — sync only when editing tokens |

More recovery detail: [`DEV.md`](DEV.md).

## Extend / configure

```bash
npm run validate:workflows          # YAML schema + known processors/steps
npm run validate:workflows -- --include-examples
```

New use case or detector? → [`EXTENDING.md`](EXTENDING.md) (templates under
`backend/workflows/examples/`). DEML control-plane compose: Pipeline Studio at
`/pipeline` (export YAML here — FORJD still owns deploy).

## Read next (when you have another 20 minutes)

1. [`EXTENDING.md`](EXTENDING.md) — workflows, detectors, add-ons, validate
2. [`ARCHITECTURE.md`](../ARCHITECTURE.md) — layers and security lanes
3. [`AGENTS.md`](../AGENTS.md) — invariants agents and humans must not break
4. [`TESTING.md`](TESTING.md) — unit / e2e / CI map
5. [`CONFIGURATION.md`](CONFIGURATION.md) — env catalog
6. [`PRODUCTION_DEPLOY.md`](PRODUCTION_DEPLOY.md) — when you leave the laptop
