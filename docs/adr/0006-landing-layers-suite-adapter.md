# ADR-0006: Landing layers + forjd-ui suite adapter

## Status

**Superseded** — 2026-08-04

The Angular product landing (`frontend/`, forjd-ui, forjd.co) was removed. FORJD is
API-only at backend.forjd.co. Visual chrome for HTML shells uses deml-ui (warm ash).
Community narrative: dataengineeringformachinelearning.com.

## Context (historical)

FORJD’s product UI was a **static landing** (no console). Suite chrome matched
DEML Viking-UI via a forjd-ui adapter.

## Decision (current)

- No product frontend in this repo
- backend.forjd.co splash/docs/redoc → vendored deml-ui + `forjd-backend.css`
- Public story → community marketing site + deml.app

## Consequences

- Do not reintroduce forjd-ui, Viking suite CSS, or a forjd.co Vercel deploy
- See `docs/SUITE_UI_UNIFICATION.md`
