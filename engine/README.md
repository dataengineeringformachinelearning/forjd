# FORJD engine on Fly.io

Standalone Rust HTTP service for `forjd-engine` (Arrow/Parquet process + summarize).
The Python extension path (maturin / in-process) is unchanged — Compose/Fly prefer this binary.

## Prerequisites

- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) logged in (`fly auth login`)
- Docker available for local image builds (Fly remote builders work without a local daemon)

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (no external deps yet) |
| GET | `/v1/version` | Crate + schema version |
| POST | `/v1/process` | Validate/enrich event (auth when token set) |
| POST | `/v1/summarize` | Arrow/Parquet summary (auth when token set) |

Security defaults:

- `ENGINE_API_TOKEN` — when set, mutate routes require `Authorization: Bearer …` or `X-Engine-Token`
- 64 KiB body limit, 30s request timeout, security response headers, request IDs

## Local binary

```bash
cd engine
cargo test
cargo test --features server --no-run
cargo run --no-default-features --features server
curl -s http://127.0.0.1:8080/health
curl -s -X POST http://127.0.0.1:8080/v1/summarize \
  -H 'Content-Type: application/json' \
  -d '{"values":[1,2,3]}'
```

With auth:

```bash
ENGINE_API_TOKEN=dev-secret cargo run --no-default-features --features server
curl -s -X POST http://127.0.0.1:8080/v1/summarize \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dev-secret' \
  -d '{"values":[1,2,3]}'
```

## Local Docker image

```bash
cd engine
docker build -t forjd-engine .
docker run --rm -p 8080:8080 -e ENGINE_API_TOKEN=dev-secret forjd-engine
```

## Deploy

```bash
cd engine
fly apps create forjd-engine          # once; rename in fly.toml if taken
fly secrets set ENGINE_API_TOKEN='…strong-token…'
fly deploy
```

Smoke-check:

```bash
fly status
curl -s https://forjd-engine.fly.dev/health
curl -s https://forjd-engine.fly.dev/v1/version
```

## Wiring other Fly apps

Prefer the private network (no public internet for app traffic):

```text
ENGINE_URL=http://forjd-engine.internal:8080
ENGINE_API_TOKEN=…same as engine secret…
```

The FastAPI backend uses HTTP when `ENGINE_URL` is set, otherwise the in-process PyO3 wheel.

## Notes

- Image is multi-stage (`rust:1.97.0-bookworm` → `debian:bookworm-slim`), `USER 1001`, pinned tags.
- Build uses `--no-default-features --features server` so the image does not need Python/PyO3.
- Arrow/Parquet **59**, PyO3 **0.29**, edition **2024**.
- Scale memory if Parquet batches grow (`fly scale memory 1024`).
- Set `RUST_LOG=debug` / `RUST_BACKTRACE=1` via secrets only when debugging.
