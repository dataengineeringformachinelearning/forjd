# FORJD

Data streaming pipeline platform. This repo’s **pulse PoC** wires the full stack end to end:

**Angular → FastAPI → Rust engine (PyO3) + Polars + Pathway + Prefect + Supabase Postgres + Dragonfly**

## Prerequisites

| Tool | Why |
|------|-----|
| [uv](https://docs.astral.sh/uv/) | Backend deps + builds the Rust engine |
| Rust (stable) | Required by maturin when building `forjd-engine` (`rustup` / Homebrew) |
| Node 20+ / npm | Frontend |
| Docker (optional) | Local Dragonfly + Prefect |
| Supabase project | Postgres (`POSTGRES_DSN`) |
| [flyctl](https://fly.io/docs/hands-on/install-flyctl/) (optional) | Deploy Dragonfly / engine |

Python is pinned to **3.14** in `backend/`. Pathway currently fails to import on 3.14; the pulse soft-fails that layer and continues.

## Quick start (local)

Open three terminals from the repo root.

### 1. Config

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

- **`POSTGRES_DSN`** — Supabase connection string, keep the `postgresql+asyncpg://…` form  
  Example: `postgresql+asyncpg://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres`
- **`REDIS_URL`** — leave `redis://localhost:6379/0` for local Compose Dragonfly

Optional: run `backend/sql/001_pulses.sql` in the Supabase SQL editor (the API can also create the table on first pulse).

### 2. Cache + Prefect (Docker)

```bash
cd backend
docker compose up -d dragonfly prefect-server
```

Optional local Postgres instead of Supabase:

```bash
docker compose --profile local-db up -d
# then set POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@localhost:5432/forjd
```

### 3. API + Rust engine

```bash
cd backend
uv sync                    # builds ../engine via maturin
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/v1/stack
curl -s -X POST http://127.0.0.1:8000/api/v1/pulse \
  -H 'Content-Type: application/json' \
  -d '{"values":[1,2,3,5,8]}'
```

- `/health` — process up  
- `/ready` — Postgres + Dragonfly both reachable  
- `/api/v1/stack` — per-layer status for the UI  

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
| Rust `forjd-engine` | Process event + Arrow/Parquet summarize |
| Polars | Batch aggregate |
| Pathway | Finite stream reduce (soft-fail on Py 3.14) |
| Prefect | `forjd-pulse` flow (local fallback if server down) |
| Postgres | Insert into `pulses` |
| Dragonfly | Cache last pulse (`forjd:pulse:last`) |

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

Private URL for other Fly apps: `http://forjd-engine.internal:8080`. Details: [`engine/README.md`](engine/README.md).

### API image

From **repo root** (includes the Rust wheel):

```bash
docker build -f backend/Dockerfile -t forjd-api .
```

Compose from `backend/`:

```bash
docker compose up --build
```

### Frontend → Vercel

`frontend/vercel.json` is set up. Set production `apiBaseUrl` in `frontend/src/environments/environment.ts` to your API origin, and add that origin to backend `CORS_ORIGINS`.

## Layout

```text
backend/     FastAPI, Prefect, Polars/Pathway services, Compose
engine/      Rust core (PyO3 + Fly HTTP binary / Dockerfile / fly.toml)
frontend/    Angular app + forjd-ui
infra/dragonfly/   Fly.io Dragonfly
infra/engine/      Pointer to engine Fly deploy docs
```

More detail: [`backend/README.md`](backend/README.md), [`AGENTS.md`](AGENTS.md), [`LOG.MD`](LOG.MD).
