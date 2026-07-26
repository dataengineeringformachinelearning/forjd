# FORJD scale architecture

Lightweight structural guidance for growing the sealed data plane. Prefer
composition and DB leases over new orchestrators.

**Stack reality:** FastAPI + Prefect 3 + Rust sealed pipeline (+ Python soft
fallback). Pathway and Airflow are **not** part of the live system.

## Bounded contexts (keep these sharp)

| Context | Owns | Do not mix in |
|---------|------|---------------|
| Sealed ingest | Acceptance receipts, ciphertext ledger | SIEM plaintext fields |
| Projections / replay | Checkpoints, DLQ, cursor polls | Browser SSE |
| SIEM / SOAR | Normalized signals, playbooks | Ciphertext evidence |
| Analytics / ML workers | Rollups, scores, training | Partner auth |
| Status | Published pages + Rust probes | DEML billing |
| Engine (Rust) | Hot-path sealed pipeline, data-plane roles | HTTP auth policy |

`domain.py` is the main blur risk — carve analytics/scanners out when a file
next needs a large edit (thin re-exports during migration).

## Horizontal scale map

| Work | Multi-machine safe? | Mechanism |
|------|---------------------|-----------|
| Ingest processing | Yes | `SKIP LOCKED` leases |
| SOAR retries / exports | Yes | `SKIP LOCKED` leases |
| Projection catch-up | Yes | `pg_try_advisory_lock` per tenant/workflow |
| Analytics rollup | **Yes (now)** | tick lease `forjd:worker:analytics-rollup` |
| ML training | **Yes (now)** | tick lease `forjd:worker:ml-training` |
| Retention | Mostly | Idempotent deletes; optional lease later |
| ML artifacts on Fly volume | **No** | Per-machine volume — move to object storage next |

## Highest-ROI refactors (ranked)

1. **Done here:** advisory leases on analytics + training ticks.
2. **Done here:** rename `pathway_sealed_process` → `sealed_process` (compat alias kept). Wire JSON key `"pathway"` remains for partner compat — migrate later.
3. **Split process roles via env** — e.g. `FORJD_RUN_WORKERS=ingest,soar,exports` on API machines vs `analytics,training` on a worker box (same image).
4. **Carve `domain.py`** into analytics / scanners / assets routers.
5. **Soft vs hard readiness** — keep Postgres/Redis/RLS on `/ready`; expose worker staleness separately so a bad ML tick does not shed API capacity.
6. **ML artifacts → object storage** (exports already have an S3 path).
7. **Bound projection tenant×workflow concurrency** with a semaphore.
8. **Thin RED metrics** (`/metrics` or structured log counters) — skip full APM/mesh.

## Observability at higher load

Already have: structured JSON logs, `X-Request-ID`, `/health` + `/ready`, optional Sentry/Rollbar.

Add next (only when load warrants):

- Request count + latency by route template
- Worker tick duration + lease skip count
- DB pool saturation gauge

## What not to build

- Pathway revival or Airflow DAGs
- Service mesh / Kubernetes-first rewrite
- FORJD-hosted browser console or SSE (partners poll / bridge)
- Premature microservices for scanners

See also: [`CONNECTION_MAP.md`](CONNECTION_MAP.md) (when present), [`ARCHITECTURE.md`](../ARCHITECTURE.md).
