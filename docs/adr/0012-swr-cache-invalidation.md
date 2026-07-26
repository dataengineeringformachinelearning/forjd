# ADR-0012: Cache invalidation and background revalidation

## Status

Accepted — 2026-07-26

## Context

The landing `/ready` probe already needed fresh hits, stale-while-revalidate, and
retry invalidation. An ad-hoc module cache raced with in-flight writes after
`invalidate`, and background revalidation updated memory without notifying the UI.
A mega multi-key SWR map was rejected earlier (ADR-0010); we still need a clear,
reusable strategy.

## Decision

1. **One `createSwrCache` per resource** under `core/fetch/swr-cache.ts` — compose
   instances; do not invent a global keyed store.
2. **Policy:** `freshMs` (serve only) → `staleMs` (serve + background revalidate) →
   miss (blocking network). Failed revalidation **keeps** the previous value.
3. **Invalidation modes:**
   - **Hard `invalidate()`** — drop value, bump generation so in-flight writes
     cannot repopulate (Retry, back online).
   - **Soft `markStale()`** — keep value, age past `freshMs` so the next read
     SWR-revalidates (tab visible again).
   - **`revalidate(fetcher)`** — force background refresh when a value exists.
4. **Subscribers** fire on successful cache writes so presentation can
   `applySettled` without a loading flash (ADR-0011).
5. **`shouldCache`** skips storage for non-durable outcomes (`offline`).
6. **`/ready` policy:** `freshMs=30s`, `staleMs=120s` (`READY_CACHE_POLICY`).

## Consequences

- New client caches use `createSwrCache` + explicit invalidate/markStale
- Landing: Retry/online → hard invalidate; visibility → markStale + silent reconcile
- Do not add TanStack Query / NgRx for this surface
- Dual-adapter mirror lives in viking-ui `core/swr-cache` for DEML adoption
