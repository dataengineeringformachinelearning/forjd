# FORJD connection map

What talks to what in the sealed data plane. There is **no Airflow** and
**no Pathway** in production — Prefect 3 + Rust sealed pipeline (+ Python soft
fallback) own streaming work.

## Topology

```
Partner / DEML BFF                 Operators (forjd.co docs only)
  │ fjsvc_ tenant token              │ Supabase user JWT
  ▼                                  ▼
FastAPI control plane (Fly: forjd-backend)
  │  Postgres (Supabase) + Dragonfly
  │  Prefect YAML workflows
  ▼
forjd-engine (Rust HTTP on Fly 6PN, or in-process PyO3)
  │  sealed pipeline / detectors / outbox helpers
  ▼
stream_results · telemetry_events (ciphertext) · security_signals
```

## Public probes

| Path | Meaning | Used by |
|------|---------|---------|
| `GET /health` | Process liveness | Operators, soft probes |
| `GET /ready` | Postgres + Redis + workers (+ optional engine info) | **Fly route admission**, DEML soft probe, landing continuity |

`/ready` returns 503 when hard checks fail. `engine` is informational — API
stays ready when the engine restarts independently.

## Resilience (kept simple)

| Concern | Pattern |
|---------|---------|
| Fly admission | HTTP check → `/ready` (grace 90s) |
| Engine probe | 2-attempt retry inside `remote_version`; readiness wraps with 1s timeout |
| Landing continuity | AbortController 2.5s; signal starts `checking`, never optimistic `ok` |
| Partner writes | Fail closed on auth/tenant mismatch; no silent Pathway fallback path |

## Env surfaces

| Deploy | Owns |
|--------|------|
| Fly `fly.api.toml` | FastAPI + workers, `ENGINE_URL`, ML volume |
| Vercel (forjd.co) | Static Angular landing only |
| Supabase | Postgres, Auth, Realtime publication |

## Runtime verification

```bash
./scripts/verify_stack_health.sh
# or
FORJD_API=https://backend.forjd.co DEML_API=https://backend.deml.app ./scripts/verify_stack_health.sh
```
