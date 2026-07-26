# FORJD

Universal secure streaming engine for sealed partner ingest, YAML workflows, and durable projections.

> **Platform boundary:** FORJD is the exclusive sealed data plane (intake, workflows,
> projections, analytics, replay, threat processing, ML). Partner apps such as
> [DEML](https://github.com/dataengineeringformachinelearning/dataengineeringformachinelearning)
> own identity, billing, consent, and product UI — they call FORJD with tenant-bound
> opaque `fjsvc_` tokens and AES-256-GCM sealed envelopes (never end-user tokens).
> Production: API/engine on **Fly** + **Supabase**; landing on **Vercel** (`forjd.co`).
> Extend workflows/detectors: [`docs/EXTENDING.md`](docs/EXTENDING.md). Partner contract:
> [DEML `docs/FORJD_INTEGRATION.md`](https://github.com/dataengineeringformachinelearning/dataengineeringformachinelearning/blob/main/docs/FORJD_INTEGRATION.md).

**New developer?** → **[`docs/START_HERE.md`](docs/START_HERE.md)** — understand the system and run it locally in about 10 minutes.

```bash
npm run bootstrap     # env + Docker Postgres/Dragonfly + uv sync + frontend install
npm run doctor        # toolchain sanity
npm run dev:api       # terminal A → http://127.0.0.1:8000
npm run dev:web       # terminal B → http://127.0.0.1:4200
npm run verify        # curl /health /ready /capabilities
```

Partners integrate with tenant-bound `fjsvc_` tokens (headless). The Angular site is a static landing — there is no operational browser console.

```text
Partner SaaS ──fjsvc_──► FastAPI (backend/) ──► Rust engine (engine/)
                              │
                     Postgres + Dragonfly
                              │
                     Landing (frontend/) — docs / suite chrome only
```

## Prerequisites

| Tool | Why |
|------|-----|
| [uv](https://docs.astral.sh/uv/) | Backend deps + builds the Rust engine |
| Rust **1.97** (`engine/rust-toolchain.toml`) | maturin / `forjd-engine` |
| Node 22.22+ / 24+ (`frontend/.nvmrc`) | Angular 22 CLI |
| Docker | Local Postgres + Dragonfly (`npm run bootstrap`) |
| Supabase (production) | Auth + Postgres + pgvector |
| [flyctl](https://fly.io/docs/hands-on/install-flyctl/) (optional) | Deploy API / engine / Dragonfly |

Python is pinned to **3.12** in `backend/` for reproducible production builds.

## Day-to-day commands

```bash
npm run doctor          # Node / uv / Rust / .env / Docker / suite paths
npm run quality         # format + lint + typecheck + suite purity
npm run quality:full    # also tests + engine clippy (CI-aligned)
npm run format          # auto-fix frontend / backend / engine
npm run install-hooks   # pre-commit + Conventional Commits (docs/GIT.md)
npm run dev:api         # API + reload → :8000
npm run dev:web         # landing → :4200
```

| Doc | When |
|-----|------|
| [`docs/START_HERE.md`](docs/START_HERE.md) | First clone / first run |
| [`docs/EXTENDING.md`](docs/EXTENDING.md) | New workflow / detector / add-on + `validate:workflows` |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`SECURITY.md`](SECURITY.md) | Contribute + report vulns |
| [`docs/DEV.md`](docs/DEV.md) | Hot reload, EMFILE, suite sync, failures |
| [`docs/GIT.md`](docs/GIT.md) | Commit messages + history |
| [`docs/TESTING.md`](docs/TESTING.md) | Unit / e2e / CI map |
| [`AGENTS.md`](AGENTS.md) · [`ARCHITECTURE.md`](ARCHITECTURE.md) | Product + architecture contract |

## Local stack details

`npm run bootstrap` copies `backend/.env.example` → `backend/.env` (local DSN + `SOFT_MIGRATE_SCHEMA=true`), starts **Dragonfly** + **Postgres** only, then syncs deps. Prefect is omitted locally so port **4200** stays free for the Angular landing.

Manual equivalent:

```bash
cp backend/.env.example backend/.env
cd backend && docker compose --profile local-db up -d dragonfly postgres
uv sync --locked
cd ../frontend && npm install
```

Optional HTTP engine container (otherwise the API uses the in-process PyO3 wheel):

```bash
cd backend && docker compose up -d forjd-engine
# ENGINE_URL=http://127.0.0.1:8080 in backend/.env
```

Production SQL `003`–`029` is for Supabase — not required for the soft-migrate laptop path. See [`backend/sql/README.md`](backend/sql/README.md).

## Secure streaming (production path)

1. Apply SQL `003`→`029` under [`backend/sql/`](backend/sql/).
2. Configure `SUPABASE_URL` / `SUPABASE_JWT_SECRET` on the API.
3. Partners authenticate with `fjsvc_…` (or Supabase user JWTs for operators), publish X25519 keys, and POST sealed batches to `/api/v1/ingest/events:batch`.
4. Rust sealed pipeline (Python fallback) processes **metadata only**; consumers use projections / Realtime.
5. Normalized SIEM signals (when needed) go to `/api/v1/siem/signals` — raw evidence stays sealed.

Details: [`backend/docs/AUTH.md`](backend/docs/AUTH.md), [`docs/PRODUCTION_DEPLOY.md`](docs/PRODUCTION_DEPLOY.md).

## Optional ML catalog

`uv sync --group ml --group ml-spiking` — fit/score under `GET /api/v1/ml/models` with real tenant inputs.

## Deploy sketches

### Dragonfly → Fly.io

```bash
fly apps create forjd-dragonfly
fly volumes create dragonfly_data --size 1 --region iad -a forjd-dragonfly
fly secrets set DFLY_requirepass='strong-password' -a forjd-dragonfly
cd infra/dragonfly && fly deploy
```

Then `REDIS_URL=redis://:strong-password@forjd-dragonfly.internal:6379/0`. Details: [`infra/dragonfly/README.md`](infra/dragonfly/README.md).

### Engine → Fly.io

```bash
cd engine
fly apps create forjd-engine
fly secrets set ENGINE_API_TOKEN='…' DATABASE_URL='…' REDIS_URL='redis://:…@forjd-dragonfly.internal:6379/0'
fly deploy   # FORJD_ROLE=all
```

Private URL: `http://forjd-engine.internal:8080`. Details: [`engine/README.md`](engine/README.md).

### API image

```bash
docker build -f backend/Dockerfile -t forjd-backend .   # from repo root
```

### Frontend → Vercel

[https://forjd.co](https://forjd.co) → API `https://backend.forjd.co`. Checklist: [`docs/PRODUCTION_CHECKLIST.md`](docs/PRODUCTION_CHECKLIST.md).

Storybook is local/Chromatic only (`cd frontend && npm run storybook`).

## Layout

```text
backend/           FastAPI, Prefect, Polars, SQL
engine/            Rust core (PyO3 + process/data-plane / Fly)
frontend/          Angular landing + forjd-ui
infra/dragonfly/   Fly.io Dragonfly
supabase/          Edge Functions + Realtime notes
docs/START_HERE.md First-run guide
```

[`LOG.MD`](LOG.MD) is an engineering journal (historical). Current architecture: `ARCHITECTURE.md` + `AGENTS.md`.

**Resources:** [GitHub](https://github.com/dataengineeringformachinelearning/forjd) · [DEML control plane](https://github.com/dataengineeringformachinelearning/dataengineeringformachinelearning)

[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Fdataengineeringformachinelearning%2Fforjd.svg?type=large&issueType=license)](https://app.fossa.com/projects/git%2Bgithub.com%2Fdataengineeringformachinelearning%2Fforjd?ref=badge_large&issueType=license)

![GitHub Repo stars](https://img.shields.io/github/stars/dataengineeringformachinelearning/forjd?style=social)
