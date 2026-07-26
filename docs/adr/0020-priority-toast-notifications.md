# ADR-0020: Priority toast notifications

## Status

Accepted — 2026-07-26

## Context

Suite surfaces already had a Sonner-style toast host, but every message
competed equally: success spam could bury a danger alert, stacks grew without
bound, and auto-dismiss did not pause while the user read. We need a
**non-intrusive** channel that still **surfaces importance**.

## Decision

1. Extend the dual-adapter `createToastStore` (forjd-ui + viking-ui) with:
   - **Priority**: `low` | `normal` | `high` | `critical` (tone defaults:
     success→low, info→normal, warning→high, danger→critical)
   - **Max visible**: 3 — lower-priority / older toasts are dropped when full
   - **Dedupe keys** — replace in-flight updates instead of stacking
   - **Duration by priority** — short lows; sticky criticals (`0` until dismiss)
   - **Hover pause / resume** — reading time without focus theft
2. Hosts expose `data-priority` + assertive live regions only for `critical`.
3. Convenience APIs: `success()` (quiet) and `critical()` (sticky).
4. Do not invent a second notification bus (no parallel snackbar / banner stack).

## Consequences

- Undo toasts (ADR-0019) use `priority: high` so they outrank quiet successes
- Callers should prefer `priority` / tone defaults over ad-hoc long timers
- Modal confirms remain for irreversible server deletes — toasts are not dialogs
