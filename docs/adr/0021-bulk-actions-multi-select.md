# ADR-0021: Bulk actions and multi-select

## Status

Accepted — 2026-07-26

## Context

List and table surfaces needed select-many + a non-modal action bar without
inventing per-page selection state or a second confirmation pattern. Server
deletes remain irreversible; client undo (ADR-0019) must not fake rollback for
those calls.

## Decision

1. Dual-adapter **`createSelectionModel`** (forjd-ui + viking-ui) tracks stable
   string ids: toggle / selectMany / setSelected / toggleAll / pruneTo /
   optional `maxSelected`.
2. **`forjd-bulk-toolbar` / `viking-bulk-toolbar`** — appears when `count > 0`;
   hosts emit `actionClick` + `clear`; chrome via `.suite-bulk-toolbar`.
3. **`forjd-table`** gains `selectable`, `selectedIds` model, `bulkActions`, and
   `bulkAction` output; select-all + per-row checkboxes; selection pruned when
   rows change. Rows should expose a stable `id`.
4. Product lists (e.g. DEML settings services/incidents) compose the same model
   + toolbar; irreversible bulk deletes use confirm dialogs (ADR-0020 toasts are
   not substitutes).

## Consequences

- Do not invent a second selection store or parallel bulk bar
- Prefer confirm for irreversible server mutations; undo stack stays local-only
- Suite CSS owns selected-row + toolbar chrome; apps bind state only
