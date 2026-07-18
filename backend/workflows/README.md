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

Resolution: `workflow_id` (incl. aliases) → `content_type`+`event_type` match
→ `default: true`. Storage always uses the **canonical** workflow id and
canonical event types after alias resolution.

## Contract

| Field | Purpose |
|-------|---------|
| `id` | Stable workflow id (`workflow_id` on ingest) |
| `match.content_types` | Primary discriminator (also stored on events) |
| `match.event_types` | Optional finer routing; empty = any |
| `event_types` | Optional catalog (`EventType[]`) for UI/discovery |
| `aliases` | Partner/legacy wire ids → this workflow (config only) |
| `encryption` | Allowed modes/algos (fail closed; E2EE only today) |
| `pipeline.processor` | Key in `app.workflows.processors.REGISTRY` |
| `pipeline.steps` | Free-form steps (`rollup` + registered detectors) |
| `pipeline.projection` / `projection_name` | Durable projection contract |
| `pipeline.detector_params` | Open map for custom detector knobs |
| `outputs.tags` | Copied into `stream_results.metadata` for consumers |

## Partner / legacy aliases

Product-specific wire names must **not** appear in engine or API code. Declare
them on the target universal workflow:

```yaml
id: threat_telemetry
aliases:
  workflow_ids:
    - partner_legacy_telemetry   # example — any partner slug
  event_types:
    threat.metric:
      - partner.metric
    threat.alert:
      - partner.alert
```

Clients may send the alias `workflow_id` / `event_type`; FORJD resolves to the
canonical family before persistence and projection filters. First-party example
YAML (`threat_telemetry.yaml`) ships **without** product-specific aliases.
Copy `examples/partner_legacy_aliases.example.yaml` into an enabled
partner-local file under this directory when a subprocessor still sends legacy
wire ids (`examples/` is not loaded by the registry).

## Add a use case

1. Copy `analytics_events.yaml` → `my_saas.yaml`.
2. Set `id`, `match.content_types` / `event_types`, thresholds, tags,
   `pipeline.projection.name`.
3. Clients send sealed envelopes with `content_type` (and optional `event_type`
   / `workflow_id`). Server stores ciphertext only.
4. Optional: add a detector in `app/workflows/detectors/` and list it in
   `pipeline.steps`, or a processor in `app/workflows/processors/`.

## Domain security APIs (optional)

Beyond YAML workflows, tenant-scoped domain routes live under `/api/v1`:

| Route prefix | Role |
|--------------|------|
| `/threat-intel` | Feed refresh, TAXII ingest, IP lookup, correlate → case/playbooks |
| `/soc` | Incident cases (`assigned_actor_id` opaque) |
| `/playbooks` | Trigger conditions + webhook actions (identity actions deferred) |
| `/exports` | Polars CSV/JSON/Parquet from `stream_results` |
| `/threat-ml` | ThreatModel train/score (`uv sync --group ml`) |
| `/lighthouse`, `/osint`, `/sites` | PageSpeed, crt.sh/HIBP, Firecrawl tech enrich |
| `/assets`, `/vulnerabilities` | Inventory + vuln ledger |
| `/analytics`, `/honeypots`, `/reports`, `/compliance` | Rollups, decoys, PDF, SOC criteria |
| `/sla/train`, `/integrations/security-alert` | SLA model + EDR-style alert ingest |

Apply `sql/011`–`012` (or soft-migrate in development).

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
| `threat_telemetry.yaml` | Example threat/telemetry vertical (not platform core; used via service token + this content_type) |
| `deml_telemetry.yaml` | DEML subprocessor (`deml.metric` / `deml.alert`, `workflow_id=deml_telemetry`) |

Platform surfaces (ingest, projections, replay/DLQ, status) stay use-case agnostic.
