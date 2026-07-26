# ADR-0023: Keyboard shortcuts for power users

## Status

Accepted — 2026-07-26

## Context

Suite surfaces already bind ⌘K / `/` (search) and ⌘Z / redo (history), but
there was no shared catalog, help UI, or written reference. Power users need
discoverable chords without inventing a second global keydown framework or
stealing keys while typing.

## Decision

1. Dual-adapter **`createShortcutRegistry`** + **`suiteDefaultShortcuts()`**
   document Navigation / Editing / Help chords (`Mod` token → ⌘ or Ctrl).
2. **`?`** opens **`forjd-shortcut-help` / `viking-shortcut-help`** via
   `bindShortcutHelpKey` (skipped in editable fields).
3. Feature owners **keep their own listeners** (search palette, command
   history); the registry is the documentation SoT, not a second event bus.
4. Human docs live in [`docs/KEYBOARD_SHORTCUTS.md`](../KEYBOARD_SHORTCUTS.md);
   in-app help and search-palette footers point at the same catalog.

## Consequences

- New chords: register in the catalog **and** bind where the feature lives
- Do not invent a parallel hotkey manager or capture keys in form fields
- Undo remains confirm-free only for reversible client actions (ADR-0019)
