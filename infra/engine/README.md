# FORJD engine Fly.io pointer

Fly app config and Dockerfile live next to the crate:

- [`../../engine/fly.toml`](../../engine/fly.toml)
- [`../../engine/Dockerfile`](../../engine/Dockerfile)
- Deploy docs: [`../../engine/README.md`](../../engine/README.md)

```bash
cd engine
fly apps create forjd-engine
fly deploy
```

Dragonfly (cache) remains under [`../dragonfly/`](../dragonfly/).
