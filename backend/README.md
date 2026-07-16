# FORJD backend

FastAPI API that ties the stack together for the pulse PoC:

`Angular → FastAPI → Rust (PyO3) + Polars + Pathway + Prefect + Supabase Postgres + Dragonfly`

## Local (uv)

```bash
# From backend/ — builds ../engine via maturin
uv sync
cp .env.example .env   # set POSTGRES_DSN to Supabase; REDIS_URL to local Dragonfly

# Optional: Compose for Dragonfly + Prefect (Postgres via Supabase by default)
docker compose up -d dragonfly prefect-server

uv run forjd
# or: uv run uvicorn app.main:app --reload --port 8000
```

### Supabase

1. Create a project and copy the connection string (prefer pooler for serverless; direct is fine for this API).
2. Set `POSTGRES_DSN=postgresql+asyncpg://…` in `.env` (keep the `+asyncpg` form — clients normalize it).
3. Run `sql/001_pulses.sql` in the SQL editor (or let `POST /api/v1/pulse` auto-create the table).

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET | `/ready` | Postgres + Dragonfly |
| GET | `/api/v1/stack` | Layer status for the UI |
| POST | `/api/v1/pulse` | Run one connected pulse |
| GET | `/api/v1/pulse` | Cached last pulse + recent rows |

## Docker image

Build from **repo root** (engine + backend):

```bash
docker build -f backend/Dockerfile -t forjd-api .
```

Compose (from `backend/`):

```bash
docker compose up --build
# optional local Postgres instead of Supabase:
docker compose --profile local-db up --build
```

## Dragonfly (Fly.io)

See [`../infra/dragonfly/README.md`](../infra/dragonfly/README.md). Point `REDIS_URL` at `redis://:PASSWORD@forjd-dragonfly.internal:6379/0`.

## Notes

- **Pathway** currently fails to import on CPython **3.14** (upstream). The pulse soft-fails that layer and continues; other layers still run.
- Rust engine: `forjd-engine` (PyO3). Rebuild with `uv sync` after engine changes.
