# ADR-0009: Graceful offline handling for the landing

## Status

Accepted — 2026-07-26

## Context

FORJD’s product surface is a **static landing**, not an offline-first console.
Partners own their own clients and data plane. Still, visitors hit airplane mode
and flaky networks; conflating that with “API down” is noisy, and blasting
Sentry/Rollbar while offline wastes quota.

## Decision

1. **Graceful offline, not a sync product.** No offline sealed ingest, queue, or
   IndexedDB event store on forjd.co.
2. Distinguish **`offline`** from **`unreachable` / `not_ready`** in the `/ready`
   probe (`navigator.onLine` + fetch failure while offline).
3. Landing listens for `online`/`offline`: show a warning callout offline; auto
   re-probe when connectivity returns. Product copy remains readable.
4. Angular service worker keeps prefetching the app shell (+ hero mark); navigation
   URLs fall back to `index.html` for offline reloads of the SPA.
5. Defer monitoring/analytics init until online; skip offline readiness breadcrumbs.

## Consequences

- Theme toggle continues to work offline (local persistence + ADR-0008 rollback)
- External Swagger/ReDoc/DEML links still need network — copy says so
- Do not invent a partner offline SDK here; see DEML/FORJD integration docs
