# ADR-0006: Landing layers + forjd-ui suite adapter

## Status

Accepted — 2026-07-26

## Context

FORJD’s product UI is a **static landing** (no console). Suite chrome must match
DEML Viking-UI. Dumping fetch/Sentry/copy into the Angular component and inventing
a second design system both recreate the drift we already paid to remove.

## Decision

### App layers (landing-only)

| Layer | Path | Owns |
|-------|------|------|
| Presentation | `frontend/src/app/landing/` | Signals, template, forjd-ui composition |
| Content | `landing.content.ts` | Static narrative + suite link builders |
| Use cases / infra | `frontend/src/app/core/` | `/ready` probe, SWR, monitoring, idle bootstrap |
| Primitives | `libs/forjd-ui/` | Headless + suite classes — **no** `environment` / API |

### Suite adapter

- Visual SoT: DEML Viking-UI (`--suite-*`); FORJD vendors via `npm run sync:suite`
- `forjd-ui` is a **`--fj-*` adapter**, not a fork or Material/shadcn runtime
- Law: `docs/SUITE_UI_UNIFICATION.md`; app layer table: `frontend/src/app/README.md`

## Consequences

- Components must not implement `/ready` or assemble monitoring DSNs
- Landing readiness uses a **single-slot** probe cache (not a multi-key global SWR map); UI state is local `signal` + derived `computed`
- New reusable UI lands in forjd-ui first; app only composes
- Public Storybook host retired — local/Chromatic only
