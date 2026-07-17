# forjd-daemon

FORJD role-selected Rust data plane (migrated from DEML `deml-daemon`).

**Bus:** Dragonfly Streams via `REDIS_URL` (no Redpanda/Kafka).  
**Durability:** Postgres outbox (`outbox_events`) + `LISTEN forjd_outbox`.  
**Schema:** apply `backend/sql/009_daemon_data_plane.sql` after `008`.

One compiled binary; choose the role with `FORJD_ROLE`:

| Role | Purpose |
|------|---------|
| `relay` | Lease `outbox_events` → Dragonfly Streams (`XADD`) |
| `scheduler` | Durable UTC buckets → native cleanup or `internal-tasks` stream |
| `probe` | Bounded HTTP probes for `status_services.probe_url` |
| `normalizer` | Consume `telemetry-raw` stream → `endpoint_observations` |
| `ingest` | Axum high-volume edge → outbox (+ Dragonfly rate limits) |
| `cpe` | CPE dictionary lookups from Dragonfly |
| `all` | Local/dev: run every role in one process |

## Local run

```bash
cd engine/daemon
cp .env.example .env   # set DATABASE_URL, REDIS_URL, FORJD_ROLE
cargo test
cargo run
```

## Docker

```bash
cd engine/daemon
docker build -t forjd-daemon .
docker run --rm \
  -e FORJD_ROLE=relay \
  -e DATABASE_URL=postgresql://… \
  -e REDIS_URL=redis://:…@dragonfly:6379/0 \
  -p 8080:8080 forjd-daemon
```

## HTTP surface

| Path | When | Purpose |
|------|------|---------|
| `GET /health` | always | Liveness |
| `GET /ready` | always | Readiness (DB / Redis as configured) |
| `POST /api/v1/ingest` | `ingest` | High-volume telemetry → `outbox_events` |
| `POST /unique` | `cpe` | CPE unique lookup |

`forjd-engine` (Arrow/Parquet process + summarize) remains the separate HTTP service under `engine/`.
