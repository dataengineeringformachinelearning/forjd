# FORJD engine (Rust)

One crate, one binary, one Fly app: **Arrow/Parquet process + data plane**.

| Feature | Cargo flag | Role |
|---------|------------|------|
| Library / PyO3 | `python` / `extension-module` | In-process from FastAPI (maturin) |
| HTTP process/summarize | `server` | `/v1/process`, `/v1/summarize` |
| Data plane | `data-plane` (implies `server`) | Outbox relay, ingest edge, probes, normalizer, scheduler |

Fly/Compose build: `--features server,data-plane`.

## Endpoints

| Method | Path | When | Purpose |
|--------|------|------|---------|
| GET | `/health` | always | Liveness |
| GET | `/ready` | always | Readiness (Postgres when data plane HTTP is up) |
| GET | `/v1/version` | always | Crate + schema version |
| POST | `/v1/process` | always | Validate/enrich event |
| POST | `/v1/summarize` | always | Arrow/Parquet summary |
| POST | `/v1/sealed/pipeline` | always | Ciphertext-safe detectors → `stream_results` rows |
| POST | `/api/v1/ingest` | `FORJD_ROLE` includes ingest/`all` | Sealed edge → `outbox_events` (ciphertext required) |
| POST | `/unique` | `FORJD_ROLE=cpe` only | Optional CPE lookup |

## `FORJD_ROLE`

| Value | Behavior |
|-------|----------|
| unset / `engine` / `none` | Process HTTP only |
| `all` | Relay + scheduler + probe + normalizer + ingest |
| `relay` / `scheduler` / `probe` / `normalizer` / `ingest` | Single background role |
| `cpe` | Optional CPE plugin (not included in `all`) |

Secrets when the data plane is active: `DATABASE_URL` (or `POSTGRES_DSN`), `REDIS_URL` (Dragonfly).

Bus roles (`relay` / `scheduler` / `normalizer` / `all`) on Fly also require
internode AES-256-GCM keys:

```bash
FORJD_INTERNODE_ENCRYPTION=required
FORJD_INTERNODE_ACTIVE_KID=v1
FORJD_INTERNODE_KEYS='{"v1":"<base64url-32-bytes>"}'
```

Use `./scripts/sync_engine_dataplane_secrets.sh` to copy DSNs from
`forjd-backend`, mint keys, and set `FORJD_ROLE=all`. Without internode keys,
`all` fails closed at startup (historically the Fly crash-loop cause).

## Local binary

```bash
cd engine
cp .env.example .env
cargo test --no-default-features --features server,data-plane
FORJD_ROLE=engine cargo run --no-default-features --features server,data-plane
curl -s http://127.0.0.1:8080/health
curl -s -X POST http://127.0.0.1:8080/v1/summarize \
  -H 'Content-Type: application/json' \
  -d '{"values":[1,2,3]}'
```

## Docker

```bash
cd engine
docker build -t forjd-engine .
docker run --rm -p 8080:8080 \
  -e ENGINE_API_TOKEN=dev-secret \
  -e FORJD_ROLE=engine \
  forjd-engine
```

## Fly.io

```bash
cd engine
fly apps create forjd-engine          # once
fly secrets set ENGINE_API_TOKEN='…'  # required in prod / on Fly
fly deploy                            # starts with FORJD_ROLE=engine (process only)
# After SQL 009–010 and backend DSNs exist:
./scripts/sync_engine_dataplane_secrets.sh   # DSNs + internode keys + FORJD_ROLE=all
```

VM defaults: `shared-cpu-2x` / 2GB (process + data plane). Scale further if needed:

```bash
fly scale memory 4096 --app forjd-engine
```

Private wiring for the backend:

```text
ENGINE_URL=http://forjd-engine.internal:8080
ENGINE_API_TOKEN=…same as engine secret…
```

Apply `backend/sql/009`–`010` for outbox / API keys / audit before enabling `FORJD_ROLE=all`.

### Role stability checklist

| Role | Needs | Stable when |
|------|-------|-------------|
| `engine` | `ENGINE_API_TOKEN` | Process `/v1/process` + `/v1/summarize` only |
| `ingest` | DB + Redis | Sealed edge → `outbox_events` |
| `relay` / `scheduler` / `normalizer` | DB + Redis + internode keys | Bus encrypt/decrypt works |
| `all` | All of the above | `/ready` reports ok; logs show `data plane role=All` |
| `probe` | DB | Probe loop without bus |

Rollback: `fly secrets set FORJD_ROLE=engine -a forjd-engine`.

## Notes

- Multi-stage image (`rust:1.97.0-bookworm` → `debian:bookworm-slim`), `USER 1001`.
- PyO3 path stays lean (no `data-plane` deps).
- Arrow/Parquet **59**, edition **2024**, rustc **1.97**.
- Data-plane roles live in `src/data_plane/` (outbox, ingest, probes, scheduler).
