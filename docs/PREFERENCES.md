# Suite preferences

Soft UI chrome preferences for **forjd.co** and **deml.app**.

| Item | Detail |
|------|--------|
| Storage | `suite-preferences-v1` (JSON) |
| Sync | Cross-tab via `storage`; same-tab via `suite-preferences-change` |
| Open | `⌘,` / `Ctrl+,`, landing **Preferences**, DEML Account card |
| Export / import | Suite data pack JSON (ADR-0026) |
| Activity | Recent soft-chrome actions (ADR-0027) — see [`ACTIVITY.md`](ACTIVITY.md) |
| ADR | [0024](adr/0024-preferences-persist-sync.md) · [0026](adr/0026-suite-data-pack-export-import.md) · [0027](adr/0027-client-activity-log.md) |

## Fields (v1)

| Field | Values | Notes |
|-------|--------|--------|
| `theme` | `system` \| `light` \| `dark` | Mirrored to `suite-theme` for FOUC |
| `updatedAt` | epoch ms | Last-write-wins across tabs |

## Actions (not stored)

- Reset advanced disclosure sections (`suite-disclosure-v1`)
- Clear search history (`fj-search-recent-v1` / `viking-search-recent-v1`)
- Reset all → theme system + above clears
- **Export local data** → `suite-data-pack.json` (theme + disclosure + onboarding; optional recent searches)
- **Import (merge)** / **Import (replace)** → file picker; sanitizes; rejects secret-like keys

## Suite data pack (v1)

```json
{
  "kind": "suite-data-pack",
  "version": 1,
  "exportedAt": 0,
  "preferences": { "theme": "system", "updatedAt": 0 },
  "disclosure": {},
  "onboarding": {},
  "recentSearches": []
}
```

Browser download / upload only. Not related to server `/api/v1/exports`.

## Never store

`fjsvc_`, JWTs, API keys, session/auth flags, cookie consent, widget device IDs,
or any ciphertext.
