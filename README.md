# FORJD

Universal secure streaming engine for sealed partner ingest, YAML workflows, and durable projections.

**Static Angular landing → FastAPI control plane → Rust engine (HTTP or PyO3) + Polars + Prefect + Supabase Postgres/pgvector + Dragonfly.** Partners integrate with tenant-bound `fjsvc_` tokens (headless); there is no operational browser console.

## Prerequisites

| Tool | Why |
|------|-----|
| [uv](https://docs.astral.sh/uv/) | Backend deps + builds the Rust engine |
| Rust **1.97** (`engine/rust-toolchain.toml`) | maturin / `forjd-engine` |
| Node 22.22+ / npm | Frontend (Angular 22 CLI floor) |
| Docker (optional) | Local Dragonfly + Prefect + engine HTTP |
| Supabase project | Postgres (`POSTGRES_DSN`) — primary DB for FORJD; optional partner control-plane co-location into a non-`public` schema (see [`docs/NEON_TO_SUPABASE.md`](docs/NEON_TO_SUPABASE.md)) |
| [flyctl](https://fly.io/docs/hands-on/install-flyctl/) (optional) | Deploy Dragonfly / engine |

Python is pinned to **3.12** in `backend/` for reproducible production builds.

## Quick start (local)

Open three terminals from the repo root.

### 1. Config

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

- **`POSTGRES_DSN`** — Supabase connection string, keep the `postgresql+asyncpg://…` form  
  Example: `postgresql+asyncpg://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres`
- **`REDIS_URL`** — leave `redis://:forjd-dev-local@localhost:6379/0` for local Compose Dragonfly
- Optional harden: set **`API_KEY`** / **`ENGINE_API_TOKEN`** (Compose wires the latter into API + engine)

Apply production SQL from `003` through `026` (see [`backend/sql/README.md`](backend/sql/README.md)).

### 2. Cache + Prefect + engine (Docker)

```bash
cd backend
docker compose up -d dragonfly prefect-server forjd-engine
```

Optional local Postgres instead of Supabase:

```bash
docker compose --profile local-db up -d
# then set POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@localhost:5432/forjd
```

### 3. API + Rust engine

```bash
cd backend
uv sync                    # builds ../engine via maturin (PyO3 fallback)
# Prefer HTTP engine from Compose:
#   ENGINE_URL=http://127.0.0.1:8080
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
curl -s http://127.0.0.1:8000/api/v1/capabilities
```

- `/health` — process up  
- `/ready` — Postgres + Dragonfly (+ supervised workers) reachable  
- `/api/v1/capabilities` — machine-readable product contract  

### 4. Frontend

```bash
cd frontend
npm install
npm start
```

Open [http://localhost:4200](http://localhost:4200) for the static product landing (docs links only — nothing runnable in the UI). Dev builds point at `http://127.0.0.1:8000` via `src/environments/environment.development.ts`.

### 5. Engine only (optional)

```bash
cd engine
cargo test
cargo run --no-default-features --features server   # HTTP on :8080
# or rebuild Python bindings from backend/: uv sync
```

## Secure streaming (Supabase Auth + E2EE)

Production path for sealed partner ingress:

1. Apply SQL `003`→`026` under [`backend/sql/`](backend/sql/) (tenants, RLS, sealed events, projections/DLQ, service accounts, Realtime, ML, replay-safe SIEM/SOAR, durable exports, ingest-processing recovery, and partner provision).
2. Configure `SUPABASE_URL` / `SUPABASE_JWT_SECRET` on the API (see `backend/.env.example`).
3. Clients authenticate with Supabase Auth **or** a tenant service token (`fjsvc_…`), publish X25519 public keys (`POST /api/v1/sessions`), derive AES-256 via ECDH+HKDF, and use canonical partner batch `POST /api/v1/ingest/events:batch` with envelopes + `content_type` (YAML workflow in [`backend/workflows/`](backend/workflows/); partner wire ids via YAML `aliases`).
4. Rust sealed pipeline (dependency-free Python fallback) processes **metadata only**; consumers poll `GET /api/v1/projections` or Realtime on `stream_results`. Partner SaaS apps call FORJD as a subprocessor — see [`backend/docs/AUTH.md`](backend/docs/AUTH.md).
5. When content-aware SIEM is required, the trusted partner separately submits
   strict normalized, PII-minimized signals to `/api/v1/siem/signals`; raw
   evidence remains sealed. Cases and durable playbook runs stay tenant-scoped.

Details: [`backend/sql/README.md`](backend/sql/README.md), [`backend/README.md`](backend/README.md), and [`docs/PRODUCTION_DEPLOY.md`](docs/PRODUCTION_DEPLOY.md).

## Optional ML catalog

Install with `uv sync --group ml`. Tenant-scoped fit/score under `GET /api/v1/ml/models` (LSTM-AE, Isolation Forest, OCSVM, RF/HGB, Transformer AE, TFT-lite, NeuralSeasonal, GRU/LSTM P99, EventEncoder, NorseSSN). Optional: `ml-spiking` (norse), `ml-nlp` (sentence-transformers).

## Deploy sketches

### Dragonfly → Fly.io

```bash
fly apps create forjd-dragonfly
fly volumes create dragonfly_data --size 1 --region iad -a forjd-dragonfly
fly secrets set DFLY_requirepass='strong-password' -a forjd-dragonfly
cd infra/dragonfly && fly deploy
```

GitHub/Fly dashboard: working directory `infra/dragonfly`, config path `fly.toml` (not a doubled path). Create the volume before the first deploy — missing volume is a common failure.

Then point the API at:

```text
REDIS_URL=redis://:strong-password@forjd-dragonfly.internal:6379/0
```

Details: [`infra/dragonfly/README.md`](infra/dragonfly/README.md).

### Engine → Fly.io

Unified Rust service (process / summarize + data plane via `FORJD_ROLE`). Config lives in `engine/`:

```bash
cd engine
fly apps create forjd-engine
fly secrets set ENGINE_API_TOKEN='…' DATABASE_URL='…' REDIS_URL='redis://:…@forjd-dragonfly.internal:6379/0'
fly deploy   # shared-cpu-2x / 2GB; FORJD_ROLE=all
```

Private URL for other Fly apps: `http://forjd-engine.internal:8080`. Set matching `ENGINE_URL` + `ENGINE_API_TOKEN` on the API. Details: [`engine/README.md`](engine/README.md).

### API image

From **repo root** (includes the Rust wheel):

```bash
docker build -f backend/Dockerfile -t forjd-backend .
```

Compose from `backend/`:

```bash
docker compose up --build
```

### Frontend → Vercel

Domain: [https://forjd.co](https://forjd.co). `frontend/vercel.json` ships CSP and browser hardening headers. Production `apiBaseUrl` is `https://backend.forjd.co` — point that hostname at Fly (`forjd-backend`) and keep `https://forjd.co` in backend `CORS_ORIGINS`.

API CSRF is **header auth** (`Authorization` / `X-API-Key`), not CSRF tokens; XSS hardening is middleware CSP on the API plus SPA headers — see [`backend/docs/AUTH.md`](backend/docs/AUTH.md).

Production deploy (SQL, mint `fjsvc_`, Fly/Vercel checklist): see [`docs/PRODUCTION_DEPLOY.md`](docs/PRODUCTION_DEPLOY.md) and [`docs/PRODUCTION_CHECKLIST.md`](docs/PRODUCTION_CHECKLIST.md).

**Engine data plane:** `FORJD_ROLE=engine` is process-only; `all` needs DSNs **and** internode keys (`./scripts/sync_engine_dataplane_secrets.sh`).

**Postgres:** Production uses Supabase. Optional partner control-plane co-location into a non-`public` schema: controlled ETL [`docs/NEON_TO_SUPABASE_ETL.md`](docs/NEON_TO_SUPABASE_ETL.md) (preferred) or dump/restore [`docs/NEON_TO_SUPABASE.md`](docs/NEON_TO_SUPABASE.md). Verify with `scripts/neon_supabase_etl/verify_etl.py` + `backend/scripts/verify_supabase_post_migration.py`.

### Storybook → Vercel (ui.forjd.co)

Public forjd-ui Storybook: [https://ui.forjd.co](https://ui.forjd.co). Separate Vercel project (`ui`) — see [`frontend/README.md`](frontend/README.md). Attach the `ui.forjd.co` domain after the first production deploy.

### API custom domain

```bash
fly certs add backend.forjd.co -a forjd-backend
# In Vercel DNS for forjd.co, add the A/AAAA Fly prints (→ forjd-backend)
```

## Layout

```text
backend/           FastAPI, Prefect, Polars, SQL
engine/            Rust core (PyO3 + process/data-plane / Fly)
frontend/          Angular app + forjd-ui
infra/dragonfly/   Fly.io Dragonfly
supabase/          Edge Functions + Realtime notes
```

More detail: [`backend/README.md`](backend/README.md) and [`AGENTS.md`](AGENTS.md). [`LOG.MD`](LOG.MD) is an engineering journal (historical); current architecture lives in `ARCHITECTURE.md` and `AGENTS.md`.
