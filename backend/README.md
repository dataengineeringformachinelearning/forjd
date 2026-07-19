# FORJD backend

FastAPI control plane for the universal secure streaming engine:

`Partners / UI docs → FastAPI → Rust (PyO3 or HTTP) + Polars + Pathway + Prefect + Supabase Postgres + Dragonfly`

The API root (`GET /`) is a static landing with docs links only. Product work happens through authenticated `/api/v1/*` routes (service tokens / JWTs) — not through an in-browser run console.

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
3. Apply SQL `003`→`025` (see [`sql/README.md`](sql/README.md)). Enable the **vector** extension for optional ML.
4. For the ML catalog: install torch with `uv sync --group ml`.

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Static API landing (docs links) |
| GET | `/health` | Liveness |
| GET | `/ready` | Postgres + Dragonfly + supervised workers (+ object storage in production) |
| GET | `/api/v1/capabilities` | Machine-readable product contract |
| GET/POST | `/api/v1/tenants` | List / create tenants (enterprise user JWT) |
| GET/POST/DELETE | `/api/v1/service-accounts` | Mint / list / revoke tenant-scoped M2M tokens |
| POST | `/api/v1/ingest` | Sealed event ingest (user JWT or service token) |
| POST | `/api/v1/ingest/events` | Alias of `/ingest` |
| POST | `/api/v1/ingest/events:batch` | Canonical DEML/partner sealed batch ingest (≤25 events, ≤8 MiB request) |
| GET | `/api/v1/ingest/processing/{batch_id}` | Durable post-acceptance processing status |
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
| GET/POST | `/api/v1/siem/signals` | Filter/create tenant-idempotent, PII-minimized normalized signals |
| GET/POST/PATCH | `/api/v1/soc/cases` | Tenant case management (`PATCH` uses `/{case_id}`) |
| GET/POST/PATCH | `/api/v1/playbooks` | Versioned playbook management (`PATCH` uses `/{playbook_id}`) |
| POST | `/api/v1/playbooks/{playbook_id}/execute` | Durable idempotent manual execution |
| GET | `/api/v1/playbooks/runs` | Durable run/action state |
| POST | `/api/v1/playbooks/runs/{run_id}/actions/{result_id}/ack` | Control-plane action acknowledgement |
| POST | `/api/v1/playbooks/runs/{run_id}/actions/{result_id}/retry` | Queue an explicit bounded webhook retry |
| GET/POST | `/api/v1/exports` | List/create durable idempotent tenant exports |
| GET | `/api/v1/exports/{job_id}` | Poll export status/checksum/expiry |
| GET | `/api/v1/exports/{job_id}/download` | Create a short-lived private signed download |

Exports support CSV, JSON, Parquet, and PDF. PDF is explicitly capped at 1,000
rows; other formats page up to the requested 100,000-row limit within the
configured source/artifact byte budgets, without silent truncation.

### Secure streaming (Supabase Auth + E2EE)

1. Run SQL `003`→`025` (see [`sql/README.md`](sql/README.md)).
2. Set `SUPABASE_URL` and/or `SUPABASE_JWT_SECRET` in `.env`.
3. **Enterprise users:** Supabase Auth → `Authorization: Bearer <access_token>`.
4. **Subprocessors:** admin mints `POST /api/v1/service-accounts` → the partner calls with `Bearer fjsvc_…` (see [`docs/AUTH.md`](docs/AUTH.md)). Partners keep their own end-user auth.
5. Publish X25519 *public* keys via `POST /api/v1/sessions` (private keys stay on device / subprocessor).
6. Derive AES-256 via X25519 ECDH + HKDF; seal with AES-256-GCM; use canonical partner batch `POST /api/v1/ingest/events:batch` with `content_type` / optional `event_type` / `workflow_id`.
7. Prefect / Rust sealed pipeline write durable `stream_results`; poll `GET /api/v1/projections?since=` or Realtime; `POST /api/v1/projections/run` for catch-up.

Discover the live headless contract and exact request limits at
`GET /api/v1/capabilities`. Canonical ingest is capped before JSON parsing at
8 MiB per request and 25 events per batch; oversized requests return `413`.
Sealed acceptance also creates an ordered, version/hash-bound processing
receipt and a required tenant-scoped, metadata-only audit event in the same
transaction; an audit persistence failure rolls back acceptance. The API still attempts work synchronously;
leased workers recover crashes/restarts, and clients can poll the returned
`processing_batches[].status_path`. No `202` asynchronous contract is claimed.

**New use case:** add `workflows/my_saas.yaml` (or a detector under `app/workflows/detectors/`) — no ingest/API fork required.

Optional security, ML, and testing integrations use the disabled-by-default
[add-on system](docs/ADDONS.md). Enable a subset with `FORJD_ADDONS`, or use a
YAML profile through `FORJD_ADDONS_CONFIG`; inspect state at `GET /api/v1/addons`.

Server-minimal knowledge: Double Ratchet headers stay opaque; FastAPI never decrypts E2EE ciphertext. Self-check: `uv run python -m unittest discover -s tests -v`.

Content-aware SIEM is an explicit second lane, not a decryption shortcut. A
trusted partner submits only normalized, bounded, PII-minimized fields to
`/api/v1/siem/signals`; raw evidence stays sealed. In production, configure
`OUTBOUND_HOST_ALLOWLIST` before using custom TAXII feeds or webhook actions.
Webhook playbooks may store an opaque `secret_ref`; resolve its HMAC key from
the deployment-secret `WEBHOOK_SIGNING_SECRETS_JSON` mapping. Missing refs fail
without sending an unsigned request, and secret values are never persisted or
returned.

The compatibility `POST /api/v1/integrations/security-alert` route now requires
`client_alert_id` and timezone-aware `observed_at` and delegates to the same
idempotent normalized-signal core. New integrations should call
`POST /api/v1/siem/signals` directly.

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

```

Torch stays in the optional `ml` dependency group so slim API images stay small.

## Docker image

Build from **repo root** (engine + backend + ML group):

```bash
docker build -f backend/Dockerfile -t forjd-backend .
```

The image installs the `ml` and object-storage dependency groups (CPU torch +
S3 client) and mounts checkpoints at `ML_MODEL_DIR` (`/data/models` on Fly).

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
