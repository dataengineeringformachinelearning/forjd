# FORJD Dragonfly on Fly.io

Redis-compatible cache for the API (`REDIS_URL`). Postgres stays on **Supabase**.

## Prerequisites

- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) logged in (`fly auth login`)
- A Fly org that can create apps + volumes

## Deploy

```bash
cd infra/dragonfly
fly apps create forjd-dragonfly          # once; rename in fly.toml if taken
fly volumes create dragonfly_data --size 1 --region iad
fly secrets set DFLY_requirepass='replace-with-strong-password'
fly deploy
```

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

- Prefer **`.internal`** (no public internet). Public `services.ports` is for optional debugging.
- Pin the image tag in `fly.toml` (no `:latest`).
- Scale memory if you cache large payloads (`fly scale memory 1024`).
