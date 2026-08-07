# FORJD

Universal secure streaming engine — sealed partner ingest, YAML workflows, and durable projections.

| Repo | Role | Production |
|------|------|------------|
| [`deml`](https://github.com/dataengineeringformachinelearning/deml) | Control plane | [deml.app](https://deml.app) · [backend.deml.app](https://backend.deml.app) |
| [`deml-ui`](https://github.com/dataengineeringformachinelearning/deml-ui) | Design system (warm ash NFTS) | [ui.deml.app](https://ui.deml.app) |
| **This repo (`forjd`)** | Data plane | Fly → [backend.forjd.co](https://backend.forjd.co) |
| [`dataengineeringformachinelearning`](https://github.com/dataengineeringformachinelearning/dataengineeringformachinelearning) | Community / BOOK / blog / docs | [dataengineeringformachinelearning.com](https://dataengineeringformachinelearning.com) |

## Owns

- Sealed ingest, streaming, projections, replay/DLQ, analytics, ML, status pages, threat/SIEM paths
- FastAPI (`backend/`) + Rust engine (`engine/`) + Postgres + Dragonfly
- Partner auth via tenant-bound `fjsvc_` tokens and AES-256-GCM sealed envelopes — **never** end-user tokens

API-only product surface: splash on `backend.forjd.co` (vendored deml-ui). Human docs live on the community site (`/documentation`).

```text
Partner SaaS ──fjsvc_──► FastAPI (backend/) ──► Rust engine (engine/)
                              │
                     Postgres + Dragonfly
```

## Run

**New developer?** → [`docs/START_HERE.md`](docs/START_HERE.md)

```bash
npm run bootstrap     # env + Docker Postgres/Dragonfly + uv sync + deml-ui sync
npm run doctor
npm run dev:api       # → http://127.0.0.1:8000
npm run verify        # curl /health /ready /capabilities
```

## Check

```bash
npm run quality         # catalog + ruff
npm run quality:full    # + tests + engine clippy
npm run install-hooks   # pre-commit + Conventional Commits
npm run sync:deml-ui    # vendor deml-ui CSS into backend/static
```

## Deploy

| Host | Platform | Notes |
|------|----------|-------|
| `backend.forjd.co` | Fly (`forjd-backend` / `forjd-engine` / `forjd-dragonfly`) | [`docs/PRODUCTION_DEPLOY.md`](docs/PRODUCTION_DEPLOY.md) |

### Prerequisites

| Tool | Why |
|------|-----|
| [uv](https://docs.astral.sh/uv/) | Backend deps + builds the Rust engine |
| Rust **1.97** (`engine/rust-toolchain.toml`) | maturin / `forjd-engine` |
| Docker | Local Postgres + Dragonfly (`npm run bootstrap`) |
| [flyctl](https://fly.io/docs/hands-on/install-flyctl/) (optional) | Deploy |

Python is pinned to **3.12** in `backend/`. Critical env: copy `backend/.env.example` → `backend/.env` (bootstrap does this). Inventory SoT: [`config/forjd.catalog.yaml`](config/forjd.catalog.yaml) · [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

## Layout

```text
backend/           FastAPI, Prefect, Polars, SQL + deml-ui HTML shells
engine/            Rust core (PyO3 + process/data-plane)
infra/dragonfly/   Fly.io Dragonfly
config/            forjd.catalog.yaml (env inventory SoT)
docs/START_HERE.md First-run guide
```

## Docs

| Doc | When |
|-----|------|
| [`docs/START_HERE.md`](docs/START_HERE.md) | First run |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`AGENTS.md`](AGENTS.md) | Architecture contract |
| [`docs/EXTENDING.md`](docs/EXTENDING.md) | Workflows / detectors / add-ons |
| [`backend/docs/AUTH.md`](backend/docs/AUTH.md) | Tokens + CSRF/XSS model |
| [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) | Env inventory |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`SECURITY.md`](SECURITY.md) | Contribute / vulns |

## Related

- Control plane: [`deml`](https://github.com/dataengineeringformachinelearning/deml)
- Community docs: [dataengineeringformachinelearning.com/documentation](https://dataengineeringformachinelearning.com/documentation)

[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Fdataengineeringformachinelearning%2Fforjd.svg?type=large&issueType=license)](https://app.fossa.com/projects/git%2Bgithub.com%2Fdataengineeringformachinelearning%2Fforjd?ref=badge_large&issueType=license)
