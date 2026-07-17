# FORJD workflow definitions

YAML/JSON configs drive Prefect + Pathway processing. **Add a use case by
dropping a file here** — do not fork ingest routes or crypto.

## Universal abstractions

| Concept | Model | Role |
|---------|-------|------|
| **EventType** | `app.workflows.models.EventType` | Logical event class (`name` + `content_type`) |
| **PipelineConfig** | `PipelineConfig` | Processor + ordered `steps` + detector params |
| **ProjectionDefinition** | `ProjectionDefinition` | Durable projection name/version/retention |
| **WorkflowDefinition** | top-level YAML | Ties match rules, encryption policy, pipeline, outputs |

Resolution: `workflow_id` → `content_type`+`event_type` match → `default: true`.

## Contract

| Field | Purpose |
|-------|---------|
| `id` | Stable workflow id (`workflow_id` on ingest) |
| `match.content_types` | Primary discriminator (also stored on events) |
| `match.event_types` | Optional finer routing; empty = any |
| `event_types` | Optional catalog (`EventType[]`) for UI/discovery |
| `encryption` | Allowed modes/algos (fail closed; E2EE only today) |
| `pipeline.processor` | Key in `app.workflows.processors.REGISTRY` |
| `pipeline.steps` | Free-form steps (`rollup` + registered detectors) |
| `pipeline.projection` / `projection_name` | Durable projection contract |
| `pipeline.detector_params` | Open map for custom detector knobs |
| `outputs.tags` | Copied into `stream_results.metadata` for consumers |

## Add a use case

1. Copy `analytics_events.yaml` → `my_saas.yaml`.
2. Set `id`, `match.content_types` / `event_types`, thresholds, tags,
   `pipeline.projection.name`.
3. Clients send sealed envelopes with `content_type` (and optional `event_type`
   / `workflow_id`). Server stores ciphertext only.
4. Optional: add a detector in `app/workflows/detectors/` and list it in
   `pipeline.steps`, or a processor in `app/workflows/processors/`.

Apply SQL `006`–`010` for routing, projections/DLQ, status, daemon plane, audit.

## Security (secure by default)

- Encryption policy is **E2EE-only**; ingest fails closed on mismatches.
- Processors/detectors see **metadata only** (sizes, routing) — never plaintext.
- Production (`ENVIRONMENT=prod|production` or Fly) forces RLS + crypto session binding.
- `audit_events` records ingest/security actions without ciphertext or keys.

## Example use cases

| File | Role |
|------|------|
| `default_sealed.yaml` | Generic fallback (`application/forjd-event+v1`) |
| `analytics_events.yaml` | Product analytics |
| `deml_telemetry.yaml` | Example threat/telemetry tenant config (not platform core) |

Platform surfaces (ingest, projections, replay/DLQ, status) stay use-case agnostic.
