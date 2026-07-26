# Keyboard shortcuts

Suite power-user chords for **deml.app** (product) and **forjd-ui** Storybook.
**forjd.co** is a static partner landing — it does **not** mount search,
preferences, shortcut help, or undo chrome.

Source of truth: dual-adapter `createShortcutRegistry` /
`suiteDefaultShortcuts()` (FORJD ADR-0023). Feature owners keep their own
listeners; the registry documents them.

| Chord | Action | Notes |
|-------|--------|--------|
| `⌘K` / `Ctrl+K` | Open search | Command palette (product surfaces) |
| `/` | Open search | Ignored while typing in a field |
| `Esc` | Close overlay | Search, dialogs, sheets, shortcut help |
| `⌘Z` / `Ctrl+Z` | Undo | Reversible client actions only (ADR-0019) |
| `⌘⇧Z` / `Ctrl+Shift+Z` | Redo | |
| `Ctrl+Y` | Redo | Windows / Linux alternate |
| `?` | Keyboard shortcuts | Help dialog |
| `⌘,` / `Ctrl+,` | Open preferences | Theme + local resets (ADR-0024) |

## Platform

- **macOS**: `Mod` displays as `⌘`, `Shift` as `⇧`
- **Windows / Linux**: `Mod` displays as `Ctrl`, chords join with `+`

## Extending

Register additional chords at runtime (docs + help UI only — still bind the
listener where the feature lives):

```ts
import { getDefaultShortcutRegistry } from 'forjd-ui';
// or @dataengineeringformachinelearning/viking-ui

getDefaultShortcutRegistry().register({
  id: 'my-feature',
  keys: ['Mod', 'Shift', 'P'],
  label: 'Open projections',
  group: 'Navigation',
});
```
