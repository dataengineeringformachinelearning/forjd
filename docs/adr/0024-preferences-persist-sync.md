# ADR-0024: Preferences persist and sync

## Status

Accepted — 2026-07-26

## Context

Theme, disclosure, and search history each used ad-hoc localStorage keys with
no shared sync story. Power users change appearance in one tab and expect other
tabs (and FORJD ↔ DEML suite chrome on the same origin) to follow — without a
server prefs API or storing secrets.

## Decision

1. Dual-adapter **`createPreferencesStore`** persists soft UI chrome in
   **`suite-preferences-v1`** (JSON: `theme`, `updatedAt`).
2. **Migrate** from `suite-theme` / legacy `theme` on first read; keep writing
   `suite-theme` for FOUC scripts.
3. **Sync**: `storage` events (cross-tab) + `suite-preferences-change`
   CustomEvent (same-tab). Last-write-wins via `updatedAt`. No BroadcastChannel
   for prefs (auth session keeps its own channel).
4. **UI**: `forjd-preferences` sheet / `viking-preferences` modal + Account
   Preferences card; open with **⌘,** / **Ctrl+,**.
5. **Never** store `fjsvc_`, JWTs, API keys, session flags, or ciphertext in the
   prefs blob.

## Consequences

- Theme services persist through the preferences store (`source: 'theme'`) and
  subscribe for remote updates
- Disclosure reset / clear search history are actions, not blob fields
- Density / reduced-motion remain deferred (component props / OS only)
