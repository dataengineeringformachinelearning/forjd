# Extending FORJD

Short map for partners and contributors who need a new sealed-stream use case,
detector, or add-on — without forking ingest or crypto.

YAML remains the source of truth. There is no product console and no partner
write API for workflows. Compose in DEML **Pipeline** (`/pipeline`) if you use
that control plane, then deploy the file under FORJD `backend/workflows/`.

## Choose your path

| Goal | Start here |
|------|------------|
| New sealed use case (content type + steps) | [Workflow YAML](#1-workflow-yaml) |
| Custom anomaly on ciphertext metadata | [Detectors](#2-detectors) |
| Optional integrations (OSV, HoneyDB, …) | [Add-ons](#3-add-ons) |
| Local check before deploy | [Validate](#4-validate-locally) |

Also: [`backend/workflows/README.md`](../backend/workflows/README.md) ·
[`backend/docs/ADDONS.md`](../backend/docs/ADDONS.md) ·
[`backend/docs/AUTH.md`](../backend/docs/AUTH.md) (`fjsvc_`) ·
[ADR-0028](adr/0028-yaml-workflows-validate-cli.md) · [`SECURITY.md`](../SECURITY.md).

## 1. Workflow YAML

1. Copy [`backend/workflows/examples/my_saas.example.yaml`](../backend/workflows/examples/my_saas.example.yaml)
   → `backend/workflows/my_saas.yaml` (or compose via DEML Pipeline and download).
2. Set `id`, `match.content_types`, projection name, detector thresholds, `outputs.tags`.
3. Keep `encryption.modes: [e2ee]` and `pipeline.processor: sealed_metadata`.
4. Restart / reload the API so the registry reloads the directory.
5. Clients send sealed envelopes with that `content_type` (optional `workflow_id` /
   aliases — see partner alias example under `examples/`).

`examples/` is **not** loaded at runtime. Only top-level `*.yaml` / `*.json` in
`WORKFLOWS_DIR` are.

## 2. Detectors

Metadata-only — never open event content.

1. Copy [`backend/workflows/examples/detector_stub.py.example`](../backend/workflows/examples/detector_stub.py.example)
   → `backend/app/workflows/detectors/my_detector.py`.
2. Implement `detect(events, params) -> list[dict]`.
3. Register in [`backend/app/workflows/detectors/__init__.py`](../backend/app/workflows/detectors/__init__.py)
   `REGISTRY`.
4. List the step in YAML `pipeline.steps` (+ optional `detector_params` / typed
   `size_anomaly` / `rate_anomaly` blocks).
5. Optional UI card: [`backend/app/workflows/step_cards.py`](../backend/app/workflows/step_cards.py).

### Rust vs Python

The sealed hot path lives in `engine/src/pipeline.rs` and currently runs the
built-in `size_anomaly` / `rate_anomaly` detectors. Custom Python detectors run
on the dependency-free Python soft-fallback path. For production parity, mirror
the detector in Rust or keep the step Python-only and accept fallback latency.

## 3. Add-ons

Disabled by default. Enable with `FORJD_ADDONS=slug,…` or `FORJD_ADDONS_CONFIG`
pointing at a YAML profile (`backend/config/addons/`, DEML
`infrastructure/forjd/addons.yaml`). Catalog: `GET /api/v1/addons`.
Details: [`backend/docs/ADDONS.md`](../backend/docs/ADDONS.md).

## 4. Validate locally

```bash
# From repo root — fail on parse errors + unknown processor/steps
npm run validate:workflows

# Templates under examples/
npm run validate:workflows -- --include-examples

# One file (e.g. DEML Pipeline export)
npm run validate:workflows -- ./my_saas.yaml
```

Doctor also reports how many workflow files load. Wire CI/local quality:

```bash
npm run quality   # includes validate:workflows
```

Optional runtime fail-closed: set `WORKFLOWS_STRICT=1` so unknown
processors/steps raise at registry load (not only in the CLI).

## 5. Discoverability APIs

| Endpoint | Role |
|----------|------|
| `GET /api/v1/workflows` | Catalog + `pipeline_steps` cards (auth) |
| `GET /api/v1/addons` | Add-on enablement / availability |
| `GET /api/v1/capabilities` | Partner route contract |

## Security invariants (do not break)

- Ciphertext-only lane — processors/detectors see sizes and routing metadata.
- Tenant isolation via RLS + `require_tenant_access`.
- Partners call with tenant-bound `fjsvc_` — never end-user tokens at the edge.
- Rate limiting only via `app/core/rate_limit.py`.
