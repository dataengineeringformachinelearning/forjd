# ADR-0004: Config catalog as inventory SoT

## Status

Accepted — 2026-07-26

## Context

Env vars and flags lived in `Settings`, `.env.example`, engine Rust, Fly tomls,
`.cursorrules`, and deploy docs — with drift (`ROLLBAR_ENVIRONMENT` orphan,
missing `DB_POOL_*`, Scale.md inventing unset knobs). A single Pydantic class
cannot describe engine/frontend/tooling layers.

## Decision

Split authority:

| Concern | Authority |
|---------|-----------|
| **Inventory** (names, layers, secrecy, flags) | `config/forjd.catalog.yaml` |
| **Runtime typed defaults** | `Settings` / engine env / `environment*.ts` |
| **Feature-flag view** | `app.core.feature_flags` |
| **Drift gate** | `scripts/check_config_catalog.py` (CI) |

Human guide: `docs/CONFIGURATION.md`. Ideas in `SCALE.md` are not live until
they appear in the catalog **and** a runtime owner.

## Consequences

- Adding a setting requires catalog + runtime + example in one change
- Do not invent a second settings service or remote flag SaaS
- Empty tokens / `0` intervals remain the disable pattern (ADR-0007)
