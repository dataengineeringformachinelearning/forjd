# FORJD Dragonfly on Fly.io

Redis-compatible cache for the API (`REDIS_URL`). Postgres stays on **Supabase**.

There is **nothing to compile** — deploy pulls/wraps the official Dragonfly image.
GitHub Fly often fails without a `Dockerfile` in this folder, so we ship a one-line
`FROM docker.dragonflydb.io/dragonflydb/dragonfly:v1.39.0` (same registry as Compose).

## Prerequisites

- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) logged in (`fly auth login`)
- A Fly org that can create apps + volumes

## Deploy (recommended: CLI)

```bash
# once
fly apps create forjd-dragonfly
fly volumes create dragonfly_data --size 1 --region iad -a forjd-dragonfly
fly secrets set DFLY_requirepass='replace-with-strong-password' -a forjd-dragonfly

# from this directory
cd infra/dragonfly
fly deploy
```

If deploy fails with a **volume** error, the volume was not created (or wrong region/name).

## GitHub / Fly dashboard

| Field | Value |
|-------|--------|
| Working directory | `infra/dragonfly` |
| Config path | `fly.toml` (not `infra/dragonfly/fly.toml` if working dir is set) |
| Internal port | `6379` |
| Managed Postgres | off |

Still create the volume via CLI before the first deploy succeeds.

## Wire the API

```text
REDIS_URL=redis://:replace-with-strong-password@forjd-dragonfly.internal:6379/0
```

Local proxy:

```bash
fly proxy 6379 -a forjd-dragonfly
# REDIS_URL=redis://:PASSWORD@127.0.0.1:6379/0
```

## Debug

```bash
fly status -a forjd-dragonfly
fly logs -a forjd-dragonfly
fly volumes list -a forjd-dragonfly
```
