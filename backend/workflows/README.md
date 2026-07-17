# FORJD workflow definitions

YAML/JSON configs drive Prefect + Pathway processing. **Add a use case by
dropping a file here** — do not fork ingest routes or crypto.

## Contract

| Field | Purpose |
|-------|---------|
| `id` | Stable workflow id (`workflow_id` on ingest) |
| `match.content_types` | Primary discriminator (also stored on events) |
| `match.event_types` | Optional finer routing; empty = any |
| `encryption` | Allowed modes/algos (fail closed; E2EE only today) |
| `pipeline.processor` | Key in `app.workflows.processors.REGISTRY` |
| `pipeline.steps` | Processor steps (`rollup`, `size_anomaly`, …) |
| `outputs.tags` | Copied into `stream_results.metadata` for consumers |

## Add a use case

1. Copy `analytics_events.yaml` → `my_saas.yaml`.
2. Set `id`, `match.content_types` / `event_types`, thresholds, `outputs.tags`,
   `pipeline.projection_name`.
3. Clients send `content_type` (and optional `event_type` / `workflow_id`).
4. Optional: add a detector in `app/workflows/detectors/` and list it in
   `pipeline.steps`, or a processor in `app/workflows/processors/`.

Apply SQL `006`–`008` for routing columns, durable projections/DLQ, and status pages.

## DEML cutover note

DEML’s Kafka projectors / Railway ops map here to:
- sealed ingest → `POST /api/v1/ingest`
- projectors → `POST /api/v1/projections/run` + durable `stream_results`
- DLQ/replay → `POST /api/v1/replay` + `projection_dlq`
- status pages → `/api/v1/status/*`
Keep DEML as `deml_telemetry.yaml` until Railway is torn down.
