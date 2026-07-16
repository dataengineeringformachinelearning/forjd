# FORJD engine on Fly.io

Standalone Rust HTTP service for `forjd-engine` (Arrow/Parquet process + summarize).
The Python extension path (maturin / in-process) is unchanged — this is the containerized binary.

## Prerequisites

- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) logged in (`fly auth login`)
- Docker available for local image builds (Fly remote builders work without a local daemon)

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (no external deps yet) |
| GET | `/v1/version` | Crate version |
| POST | `/v1/process` | `{"id","timestamp","payload"}` → processed event |
| POST | `/v1/summarize` | `{"values":[…]}` → Arrow/Parquet summary |

## Local binary

```bash
cd engine
cargo test
cargo run --no-default-features --features server
curl -s http://127.0.0.1:8080/health
curl -s -X POST http://127.0.0.1:8080/v1/summarize \
  -H 'Content-Type: application/json' \
  -d '{"values":[1,2,3]}'
```

## Local Docker image

```bash
cd engine
docker build -t forjd-engine .
docker run --rm -p 8080:8080 forjd-engine
```

## Deploy

```bash
cd engine
fly apps create forjd-engine          # once; rename in fly.toml if taken
fly deploy
```

Smoke-check:

```bash
fly status
curl -s https://forjd-engine.fly.dev/health
curl -s https://forjd-engine.fly.dev/v1/version
```

## Wiring other Fly apps

Prefer the private network (no public internet):

```text
ENGINE_URL=http://forjd-engine.internal:8080
```

The FastAPI backend still embeds the engine via PyO3 today; `ENGINE_URL` is for future out-of-process calls.

## Notes

- Image is multi-stage (`rust:1.97.0-bookworm` → `debian:bookworm-slim`), `USER 1001`, pinned tags.
- Build uses `--no-default-features --features server` so the image does not need Python/PyO3.
- Scale memory if Parquet batches grow (`fly scale memory 1024`).
- Set `RUST_LOG=debug` via `fly secrets` / `[env]` only when debugging.
