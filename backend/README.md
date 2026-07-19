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
| GET/POST | `/api/v1/tenants` | List / create tenants (enterprise user JWT) |
| GET/POST/DELETE | `/api/v1/service-accounts` | Mint / list / revoke tenant-scoped M2M tokens |
| POST | `/api/v1/ingest` | Sealed event ingest (user JWT or service token) |
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

1. Run SQL `003`→`015` (see [`sql/README.md`](sql/README.md)).
2. Set `SUPABASE_URL` and/or `SUPABASE_JWT_SECRET` in `.env`.
3. **Enterprise users:** Supabase Auth → `Authorization: Bearer <access_token>`.
4. **Subprocessors:** admin mints `POST /api/v1/service-accounts` → the partner calls with `Bearer fjsvc_…` (see [`docs/AUTH.md`](docs/AUTH.md)). Partners keep their own end-user auth.
5. Publish X25519 *public* keys via `POST /api/v1/sessions` (private keys stay on device / subprocessor).
6. Derive AES-256 via X25519 ECDH + HKDF; seal with AES-256-GCM; `POST /api/v1/ingest` with `content_type` / optional `event_type` / `workflow_id`.
7. Prefect / Rust sealed pipeline write durable `stream_results`; poll `GET /api/v1/projections?since=` or Realtime; `POST /api/v1/projections/run` for catch-up.

**New use case:** add `workflows/my_saas.yaml` (or a detector under `app/workflows/detectors/`) — no ingest/API fork required.

Optional security, ML, and testing integrations use the disabled-by-default
[add-on system](docs/ADDONS.md). Enable a subset with `FORJD_ADDONS`, or use a
YAML profile through `FORJD_ADDONS_CONFIG`; inspect state at `GET /api/v1/addons`.

Server-minimal knowledge: Double Ratchet headers stay opaque; FastAPI never decrypts E2EE ciphertext. Self-check: `uv run python -m unittest discover -s tests -v`.

### ML suite (optional)

Install: `uv sync --group ml` (numpy, scikit-learn, torch CPU).

| Family | Models |
|--------|--------|
| Anomaly | LSTM-AE, Isolation Forest, One-Class SVM |
| Threat | Random Forest + HistGradientBoosting, Transformer sequence AE |
| Forecasting | TFT-lite, NeuralSeasonal (Prophet-class), GRU/LSTM P99 |
| Embeddings | EventEncoder; Sentence-Transformers via `uv sync --group ml-nlp` |
| NorseSSN | Spiking temporal forecaster (`norse` via `ml-spiking`, else GRU/MLP) |

Supabase-backed: pass `tenant_id` so fit/score hydrate from `stream_results`
(metadata only) and persist to `training_runs`, `embedding_vectors` (pgvector),
and `ml_scores` (RLS + Realtime via `sql/016`).

```bash
# Catalog + fit (JWT + tenant_id → Supabase)
curl -s http://127.0.0.1:8000/api/v1/ml/models -H "Authorization: Bearer $TOKEN"
curl -s -X POST http://127.0.0.1:8000/api/v1/ml/classical_anomaly/fit \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"tenant_id":"'"$TENANT"'"}'
curl -s "http://127.0.0.1:8000/api/v1/ml/scores?tenant_id=$TENANT" \
  -H "Authorization: Bearer $TOKEN"

# Original LSTM-AE PoC endpoint (still available)
curl -s -X POST http://127.0.0.1:8000/api/v1/anomaly/fit \
  -H 'Content-Type: application/json' -d '{"use_synthetic":true,"epochs":20}'
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
