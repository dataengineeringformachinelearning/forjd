# FORJD Dragonfly on Fly.io

Redis-compatible cache for the API (`REDIS_URL`). Postgres stays on **Supabase**.

## Prerequisites

- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) logged in (`fly auth login`)
- A Fly org that can create apps + volumes

## Deploy

```bash
cd infra/dragonfly
fly apps create forjd-dragonfly          # once; rename in fly.toml if taken
fly volumes create dragonfly_data --size 1 --region iad   # required before first deploy
fly secrets set DFLY_requirepass='replace-with-strong-password'
fly deploy
```

Fly will log something like:

```text
Using build strategies '[the "docker.dragonflydb.io/…/dragonfly:v1.39.0" docker image]'
```

That is **success** for this app: there is no Dockerfile to compile. Fly pulls the
pinned official image and starts a Machine. Do **not** remove `[build]` or switch
to a Dockerfile unless you need a custom image.

Dragonfly reads `DFLY_REQUIREPASS` as `--requirepass`. Clients must include the password:

```text
redis://:replace-with-strong-password@forjd-dragonfly.internal:6379/0
```

## Wiring the API

On the backend Fly app (or any host that can reach the Fly private network):

```bash
fly secrets set REDIS_URL='redis://:PASSWORD@forjd-dragonfly.internal:6379/0'
```

Locally against a remote Dragonfly (only if you exposed TCP / use WireGuard):

```bash
# fly proxy 6379 -a forjd-dragonfly
REDIS_URL=redis://:PASSWORD@127.0.0.1:6379/0
```

## Notes

- **Private by default** — `fly.toml` has no public `services.ports`; use `.internal` / Flycast.
- Prefer **`.internal`** (no public internet). Add a public port only for temporary debugging.
- Pin the image tag in `fly.toml` (no `:latest`).
- Scale memory if you cache large payloads (`fly scale memory 1024`).
