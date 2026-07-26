# ADR-0008: Optimistic UI with rollback

## Status

Accepted — 2026-07-26

## Context

Theme preference (and future suite mutations) update the UI before persistence.
Without rollback, a failed `localStorage` write (quota / private mode) leaves the
DOM and signals ahead of durable state. A multi-key global store is unnecessary
(ADR-0006); a tiny helper is enough.

## Decision

1. Provide `runOptimistic({ snapshot, apply, persist, rollback })` in forjd-ui
   and viking-ui (`core/optimistic` dual-adapter).
2. Theme services apply preference + DOM first, then persist; on throw, restore
   the snapshot preference and re-apply DOM.
3. `FjErrorBoundary` optional `retryAction` uses the same helper (clear failed →
   action → restore failed panel on throw).
4. Landing `/ready` must **not** optimistic-ok (continuity signal stays honest).

## Consequences

- Callers always own snapshot shape; helper never holds global mutation state
- Sync and async `persist` both work; errors are returned, not rethrown
- Product mutations on DEML/FORJD should reuse this helper instead of inventing
  per-feature try/catch UI forks
