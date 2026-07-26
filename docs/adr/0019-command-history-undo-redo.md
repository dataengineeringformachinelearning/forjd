# ADR-0019: Command history for undo/redo

## Status

Accepted — 2026-07-26

## Context

Destructive or complex *client* actions (theme preference, clearing recent
searches) need a user-facing reverse path. `runOptimistic` (ADR-0008) only
rolls back failed persistence — it is not Undo. Server deletes (status pages,
API keys) stay confirm-dialog + API; inventing soft-delete here would expand
scope and security surface.

## Decision

1. Provide `createCommandHistory` / `getDefaultCommandHistory` in forjd-ui and
   viking-ui (`core/command-history` dual-adapter).
2. `run({ label, do, undo })` executes `do` first and records Undo only on
   success; `undo` / `redo` walk the stacks; max depth 40.
3. Bind **⌘Z / Ctrl+Z** (undo) and **⌘⇧Z / Ctrl+Y** (redo) once on the shared
   default history; skip when focus is in an editable field.
4. Toasts may expose an **Undo** action that calls the same stack
   (`runWithUndoToast`).
5. Wire theme preference changes and “clear recent searches” first. New
   reversible client mutations should reuse this helper — do not invent a
   second history stack.

## Consequences

- Optimistic persist failure still uses ADR-0008; history records only commits
  that succeeded
- Irreversible partner/tenant API deletes remain confirm-only (no fake Undo)
- Angular services (`FjCommandHistoryService` / `VikingCommandHistoryService`)
  expose signals for chrome; WC callers share `getDefaultCommandHistory()`
