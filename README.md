# FORJD

Data streaming pipeline platform. This repo’s **pulse PoC** wires the full stack end to end:

**Angular → FastAPI → Rust engine (HTTP or PyO3) + Polars + Pathway + Prefect + Supabase Postgres/pgvector + Dragonfly**  
(+ optional PyTorch LSTM-autoencoder anomaly PoC)

## Prerequisites

| Tool | Why |
|------|-----|
| [uv](https://docs.astral.sh/uv/) | Backend deps + builds the Rust engine |
| Rust **1.97** (`engine/rust-toolchain.toml`) | maturin / `forjd-engine` |
| Node 20+ / npm | Frontend |
| Docker (optional) | Local Dragonfly + Prefect + engine HTTP |
| Supabase project | Postgres (`POSTGRES_DSN`) |
| [flyctl](https://fly.io/docs/hands-on/install-flyctl/) (optional) | Deploy Dragonfly / engine |

Python is pinned to **3.12** in `backend/` (Pathway does not yet run on 3.14).

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

Optional: run `backend/sql/001_pulses.sql` in the Supabase SQL editor (the API can also create the table on first pulse).

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
curl -s http://127.0.0.1:8000/api/v1/stack
curl -s -X POST http://127.0.0.1:8000/api/v1/pulse \
  -H 'Content-Type: application/json' \
  -d '{"values":[1,2,3,5,8]}'

# Optional unsupervised ML PoC (LSTM-AE + pgvector)
uv sync --group ml
# then run backend/sql/002_anomaly_embeddings.sql in Supabase
curl -s -X POST http://127.0.0.1:8000/api/v1/anomaly/fit \
  -H 'Content-Type: application/json' -d '{"use_synthetic":true,"epochs":20}'
curl -s -X POST http://127.0.0.1:8000/api/v1/anomaly/score \
  -H 'Content-Type: application/json' \
  -d '{"values":[0.1,0.2,8,9,0.1,0.2,0.1,0.2,0.1,0.2,0.1,0.2,0.1,0.2,0.1,0.2]}'
```

- `/health` — process up  
- `/ready` — Postgres + Dragonfly both reachable  
- `/api/v1/stack` — per-layer status for the UI (includes optional `ml`)  
- `/api/v1/anomaly/*` — LSTM-AE fit/score + pgvector embeddings  

### 4. Frontend

```bash
cd frontend
npm install
npm start
```

Open [http://localhost:4200](http://localhost:4200). Use **Run pulse** / **Refresh stack**. Dev builds point at `http://127.0.0.1:8000` via `src/environments/environment.development.ts`.

### 5. Engine only (optional)

```bash
cd engine
cargo test
cargo run --no-default-features --features server   # HTTP on :8080
# or rebuild Python bindings from backend/: uv sync
```

## What “Run pulse” touches

| Layer | What happens |
|-------|----------------|
| Rust `forjd-engine` | Validate/enrich event + Arrow/Parquet summarize (HTTP or PyO3) |
| Polars | Batch aggregate |
| Pathway | Finite stream reduce |
| Prefect | `forjd-pulse` flow (local fallback if server down) |
| Postgres | Insert into `pulses` |
| Dragonfly | Cache last pulse (`forjd:pulse:last`) |

## Secure streaming (Supabase Auth + E2EE)

Production path for replacing Redpanda-style ingress with FORJD as the sealed pipe:

1. Apply [`backend/sql/003_secure_tenancy.sql`](backend/sql/003_secure_tenancy.sql) in Supabase (tenants, RLS, encrypted `telemetry_events`, `embedding_vectors`).
2. Configure `SUPABASE_URL` / `SUPABASE_JWT_SECRET` on the API (see `backend/.env.example`).
3. Clients authenticate with Supabase Auth and `POST /api/v1/ingest/events` with AES-256-GCM envelopes (`app.core.crypto` / Angular `src/app/crypto/seal.ts`). The server stores ciphertext only.
4. Pathway rolls up **metadata** (tenant counts / sizes) on ingest — never ciphertext. Supabase Realtime can push inserts to the UI when `supabaseAnonKey` is set.

Details: [`backend/sql/README.md`](backend/sql/README.md) and [`backend/README.md`](backend/README.md).

## Unsupervised anomaly PoC (optional)

| Piece | Role |
|-------|------|
| PyTorch LSTM-AE | Train on normal windows; reconstruction MSE = anomaly score |
| Latent vector (16-d) | Stored in Supabase **pgvector** (`anomaly_embeddings`) |
| Prefect `forjd-anomaly` | Ack fit/score (same soft-fail pattern as pulse) |
| UI | **Fit + score anomaly** on the pulse page |

Install with `uv sync --group ml`, enable `vector` in Supabase, run `backend/sql/002_anomaly_embeddings.sql`. TFT is intentionally deferred (supervised forecasting, not unsupervised detection).

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

Standalone Rust HTTP service (process / summarize). Config lives in `engine/`:

```bash
cd engine
fly apps create forjd-engine
fly deploy
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

Domain: [https://forjd.co](https://forjd.co). `frontend/vercel.json` is set up. Production `apiBaseUrl` is `https://backend.forjd.co` — point that hostname at Fly (`forjd-backend`) and keep `https://forjd.co` in backend `CORS_ORIGINS`.

### Storybook → Vercel (ui.forjd.co)

Public forjd-ui Storybook: [https://ui.forjd.co](https://ui.forjd.co). Separate Vercel project (`ui`) using `frontend/vercel.ui.json` — see `frontend/ui/README.md`. Attach the `ui.forjd.co` domain after the first production deploy.

### API custom domain

```bash
fly certs add backend.forjd.co -a forjd-backend
# In Vercel DNS for forjd.co, add the A/AAAA Fly prints (→ forjd-backend)
```

## Layout

```text
backend/     FastAPI, Prefect, Polars/Pathway services, Compose
engine/      Rust core (PyO3 + Fly HTTP binary / Dockerfile / fly.toml)
frontend/    Angular app + forjd-ui
infra/dragonfly/   Fly.io Dragonfly
infra/engine/      Pointer to engine Fly deploy docs
```

More detail: [`backend/README.md`](backend/README.md), [`AGENTS.md`](AGENTS.md), [`LOG.MD`](LOG.MD).
