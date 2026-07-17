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
4. For the unsupervised ML PoC: enable the **vector** extension, run `sql/002_anomaly_embeddings.sql`, and install torch with `uv sync --group ml`.

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET | `/ready` | Postgres + Dragonfly |
| GET | `/api/v1/stack` | Layer status for the UI |
| POST | `/api/v1/pulse` | Run one connected pulse |
| GET | `/api/v1/pulse` | Cached last pulse + recent rows |
| POST | `/api/v1/anomaly/fit` | Train LSTM-AE (synthetic normals by default) |
| POST | `/api/v1/anomaly/score` | Score a window + store latent in pgvector |
| GET | `/api/v1/anomaly` | ML status + recent embeddings |
| GET/POST | `/api/v1/tenants` | List / create tenants (Supabase JWT) |
| POST | `/api/v1/ingest` | Sealed event ingest (any use case; ciphertext only) |
| POST | `/api/v1/ingest/events` | Alias of `/ingest` |
| POST | `/api/v1/ingest/events:batch` | Batch ingest (≤100) |
| GET | `/api/v1/ingest/events?tenant_id=` | List event metadata (no ciphertext bodies) |
| GET | `/api/v1/ingest/results?tenant_id=` | Pathway/Prefect `stream_results` (+ optional `workflow_id`) |
| POST | `/api/v1/ingest/embeddings` | Tenant-scoped vectors (ML / threat features) |
| GET | `/api/v1/workflows` | List YAML/JSON workflow definitions |
| GET/POST | `/api/v1/sessions` | X25519 public session directory (JWT) |
| GET | `/api/v1/projections` | Durable projection rows |
| POST | `/api/v1/projections/run` | Advance checkpointed projections |
| POST | `/api/v1/replay` | Replay sealed metadata through a workflow |
| GET | `/api/v1/replay/dlq` | Projection DLQ |
| GET/POST | `/api/v1/status/pages` | Status pages (JWT manage) |
| GET | `/api/v1/status/pages/slug/{slug}` | Public published status page |

### Secure streaming (Supabase Auth + E2EE)

1. Run SQL `003`→`008` (see [`sql/README.md`](sql/README.md)).
2. Set `SUPABASE_URL` and/or `SUPABASE_JWT_SECRET` in `.env`.
3. Clients: sign in with Supabase Auth → `Authorization: Bearer <access_token>`.
4. Publish X25519 *public* keys via `POST /api/v1/sessions` (private keys stay on device).
5. Derive AES-256 via X25519 ECDH + HKDF; seal with AES-256-GCM; `POST /api/v1/ingest` with `content_type` / optional `event_type` / `workflow_id`.
6. Prefect `forjd-ingest` / `forjd-project` load workflows from [`workflows/`](workflows/), run Pathway + pluggable detectors, write durable `stream_results`.
7. Use `POST /api/v1/projections/run` for live catch-up, `POST /api/v1/replay` for reprocess, `/api/v1/status/*` for ops pages.

**New use case:** add `workflows/my_saas.yaml` (or a detector under `app/workflows/detectors/`) — no ingest/API fork required.

Server-minimal knowledge: Double Ratchet headers stay opaque; FastAPI never decrypts E2EE ciphertext. Self-check: `uv run python -m unittest discover -s tests -v`.

### Unsupervised ML PoC (LSTM-Autoencoder)

Uses a small PyTorch LSTM autoencoder: reconstruction MSE = anomaly score; the latent bottleneck is stored in Supabase **pgvector** for nearest-neighbor lookup. TFT is deferred — it is supervised multi-horizon forecasting, not unsupervised detection.

```bash
uv sync --group ml
# Supabase SQL editor: sql/002_anomaly_embeddings.sql (enables vector + table)

curl -s -X POST http://127.0.0.1:8000/api/v1/anomaly/fit \
  -H 'Content-Type: application/json' -d '{"use_synthetic":true,"epochs":20}'

curl -s -X POST http://127.0.0.1:8000/api/v1/anomaly/score \
  -H 'Content-Type: application/json' \
  -d '{"values":[0.1,0.2,8,9,0.1,0.2,0.1,0.2,0.1,0.2,0.1,0.2,0.1,0.2,0.1,0.2]}'
```

Torch stays in the optional `ml` dependency group so slim API images stay small; the stack check reports `ml.ok` separately from core readiness.

## Docker image

Build from **repo root** (engine + backend + ML group):

```bash
docker build -f backend/Dockerfile -t forjd-backend .
```

The image installs the `ml` dependency group (CPU torch) and mounts checkpoints at `ML_MODEL_DIR` (`/data/models` on Fly).

Compose (from `backend/`):

```bash
docker compose up --build
# optional local Postgres instead of Supabase:
docker compose --profile local-db up --build
```

## Dragonfly (Fly.io)

See [`../infra/dragonfly/README.md`](../infra/dragonfly/README.md). Point `REDIS_URL` at `redis://:PASSWORD@forjd-dragonfly.internal:6379/0`.

## API → Fly.io

Config: [`../fly.api.toml`](../fly.api.toml) (repo root — build context must include `engine/`).

```bash
# from repo root
fly apps create forjd-backend
fly volumes create ml_models --size 1 --region iad -a forjd-backend
fly secrets set POSTGRES_DSN='…' REDIS_URL='redis://:…@forjd-dragonfly.internal:6379/0' \
  ENGINE_API_TOKEN='…' ROLLBAR_ACCESS_TOKEN='…' -a forjd-backend
fly deploy --config fly.api.toml --ha=false
```

Set matching `ENGINE_URL=http://forjd-engine.internal:8080` (already in `fly.api.toml`) and the same `ENGINE_API_TOKEN` on `forjd-engine`. Enable Supabase **vector** and run `sql/002_anomaly_embeddings.sql` once before scoring in prod.

## Notes

- Backend Python is **3.12** so Pathway works (upstream + beartype still break on 3.14).
- Rust engine: `forjd-engine` (PyO3). Rebuild with `uv sync` after engine changes.
