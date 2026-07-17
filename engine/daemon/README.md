# Moved: data plane is part of `forjd-engine`

The former `forjd-daemon` binary lives inside the unified engine crate:

| Was | Now |
|-----|-----|
| `engine/daemon/` crate | `engine/src/data_plane/` module |
| `forjd-daemon` binary | `forjd-engine` (`--features server,data-plane`) |
| Separate Docker/Fly app | Same `engine/Dockerfile` + `engine/fly.toml` |

Set `FORJD_ROLE` on the engine process:

| Value | Behavior |
|-------|----------|
| unset / `engine` / `none` | Process + summarize HTTP only |
| `all` | Relay + scheduler + probe + normalizer + ingest |
| `relay` / `scheduler` / `probe` / `normalizer` / `ingest` | Single role |
| `cpe` | Optional threat-intel plugin only |

See [`../README.md`](../README.md).
