# ADR-0027: Client activity log for important soft-chrome actions

## Status

Accepted — 2026-07-26

## Context

Preferences export/import, onboarding dismiss/complete, disclosure resets, and
theme changes are important user actions with no durable local trail. Server
`audit_events` (FORJD) and DEML `AuditLog` already cover compliance writes, but
there is no list API or product UI for them — and FORJD has no product console.
Command history (ADR-0019) is an undo stack, not an activity feed.

## Decision

1. Dual-adapter **`createActivityLog`** persists a capped ring buffer in
   **`suite-activity-v1`** (max 50; newest first).
2. Entries are **metadata only**: `{ id, at, kind, label, detail?, source? }`.
   Scrub labels that look like tokens/`fjsvc_`/JWTs; reject rather than store.
3. **Sync**: `storage` + `suite-activity-change` (same pattern as preferences).
4. **UI**: `forjd-activity-list` / `viking-activity-list` in Preferences →
   **Recent activity** (also DEML Account card via shared panel).
5. **Emit from**: theme change, prefs export/import/reset, disclosure reset,
   clear search history, onboarding dismiss/complete.
6. **Do not** invent a second server audit table or mirror sealed telemetry.
   Server compliance listing of `audit_events` remains a separate later ADR.

## Consequences

- Soft chrome has a clean, scannable local trail without uploading anything
- Prefs services expose `activityEntries` + `clearActivity`
- Docs: [`docs/ACTIVITY.md`](../ACTIVITY.md)
