# ADR-0007: Sole rate limiter + FORJD_ADDONS flags

## Status

Accepted — 2026-07-26 (codifies `.cursorrules` / AGENTS invariants)

## Context

Multiple middleware limiters and ad-hoc “feature toggle” modules tend to appear
during incident response. Optional integrations (OSV, nuclei, …) must stay off by
default so slim deploys and local PoCs do not pull partner-only surface area.

## Decision

1. **Rate limiting** is implemented **only** in `app/core/rate_limit.py`, gated by
   `RATE_LIMIT_ENABLED` and per-bucket RPM settings. Do not add SlowAPI, nginx
   duplicate logic in-app, or a second Redis limiter class.
2. **Optional integrations** use the add-on registry (`app/addons/`), enabled via
   `FORJD_ADDONS` (comma slugs or `all`) or `FORJD_ADDONS_CONFIG` YAML when the
   env list is empty. Inspect at `GET /api/v1/addons`.
3. Other gates follow catalogued patterns: empty token disables sink; interval
   `0` disables worker (`feature_flags.py`).

## Consequences

- New limiters are a defect unless they replace `rate_limit.py` via a new ADR
- Partner Fly may set `FORJD_ADDONS=all`; local default remains empty
- Docs: `backend/docs/ADDONS.md`, catalog `feature_flags:` in ADR-0004
