# ADR-0026: Suite data pack export / import

## Status

Accepted — 2026-07-26

## Context

Theme, disclosure, and onboarding progress live in browser localStorage with
no portable transfer path. Users moving machines or browsers need to carry soft
UI chrome without inventing a server prefs API or touching sealed telemetry /
`/api/v1/exports` analytics jobs.

## Decision

1. Dual-adapter helpers **`exportSuiteDataPack` / `parseSuiteDataPack` /
   `applySuiteDataPack` / `downloadSuiteDataPack` / `readSuiteDataPackFile`**
   produce a browser JSON pack (`kind: "suite-data-pack"`, `version: 1`).
2. **Included by default:** preferences (theme), disclosure map, onboarding
   journey. **Optional:** recent searches (off by default — typed history).
3. **Import modes:** `merge` (union / soft overlay) or `replace` (section
   wholesale when present). Sanitize through existing store helpers; reject
   packs with secret-like top-level keys (`token`, `fjsvc`, …).
4. **UI:** Preferences panel **Export / import** section (both adapters + DEML
   Account card via shared panel). File download + `<input type="file">` only.
5. **Never** put `fjsvc_`, JWTs, API keys, auth/session flags, or ciphertext in
   the pack. Unrelated to durable server exports.

## Consequences

- Disclosure gains `snapshot` / `importMap`; onboarding gains `importState`
- Prefs services expose `exportDataPack` / `importDataPack` with toast feedback
- Docs: [`docs/PREFERENCES.md`](../PREFERENCES.md) updated
