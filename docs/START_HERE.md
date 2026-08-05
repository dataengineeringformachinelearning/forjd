# Start here (≈10 minutes)

New to FORJD? This page is the short path: understand the system, bootstrap a local stack, and prove it runs.

> **Cold vs warm:** Your *attention* stays under ~10 minutes (copy/paste + one terminal). The first `uv sync` builds the Rust engine and may wait 5–15 minutes on a quiet machine — leave it running. Later days restart in under two minutes.

## What FORJD is

FORJD is a **universal secure streaming engine**. Partners send **sealed (E2EE) events** with a tenant-bound `fjsvc_` token. FORJD stores ciphertext, runs metadata-only pipelines, and exposes projections/analytics — not a browser product console.

```text
Partner SaaS ──fjsvc_──► FastAPI (backend/) ──► Rust engine (engine/)
                              │                      │
                              ▼                      ▼
                     Postgres (Supabase/local)   Dragonfly streams
```

| Folder | Role |
|--------|------|
| `backend/` | FastAPI control plane, Prefect, Polars, SQL + deml-ui HTML shells |
| `engine/` | Rust sealed pipeline + data plane |
| `docs/` | How we work (this file, DEV, GIT, TESTING, …) |
| `AGENTS.md` / `ARCHITECTURE.md` | Product briefing + architecture contract |

Public host: **backend.forjd.co**. Community story: dataengineeringformachinelearning.com. Control plane UI: deml.app.

## Prerequisites (once per machine)

| Tool | Notes |
|------|--------|
| [uv](https://docs.astral.sh/uv/) | Backend + builds engine |
| Rust **1.97** via [rustup](https://rustup.rs/) | `rustup install 1.97` (see `engine/rust-toolchain.toml`) |
| Docker Desktop (or Engine) | Local Postgres + Dragonfly |

Optional later: Supabase project, flyctl, sibling deml-ui for CSS refresh.

## Bootstrap (one command)

From the **repo root**:

```bash
npm run bootstrap
```

That script will:

1. Check `uv` / Docker / Rust
2. Copy `backend/.env.example` → `backend/.env` if missing
3. Start **Dragonfly** + **Postgres** (`docker compose --profile local-db`)
4. `uv sync --locked` in `backend/` (builds the engine wheel)
5. Sync deml-ui CSS into `backend/static/`
6. Install git hooks (`pre-commit` + commit-msg)

Flags:

```bash
npm run bootstrap -- --skip-docker    # you already run Postgres/Redis yourself
npm run bootstrap -- --no-hooks       # skip git hook install
```

Then:

```bash
npm run doctor          # toolchain sanity
```

## Run

```bash
npm run dev:api
# → http://127.0.0.1:8000/health  ·  /ready  ·  /  ·  /docs
```

Prove it:

```bash
npm run verify
```

Guide: [`DEV.md`](DEV.md) · extend workflows: [`EXTENDING.md`](EXTENDING.md).
