# FORJD app layers

Landing-only Angular surface. Keep **business/domain logic** out of templates and
UI components; keep **presentation** out of `core/`.

**ADR:** [`docs/adr/0006-landing-layers-suite-adapter.md`](../../../docs/adr/0006-landing-layers-suite-adapter.md).

| Layer          | Path                                                                                                               | Owns                                                                            | Must not                                                        |
| -------------- | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Presentation   | `landing/`, `app.ts`                                                                                               | Signals, template bindings, forjd-ui composition                                | `fetch`, SWR, Sentry/Rollbar, readiness protocol                |
| Content        | `landing/landing.content.ts`                                                                                       | Static copy + suite link builders                                               | Network / monitoring                                            |
| Use cases      | `core/ready/landing-ready.ts`                                                                                      | Landing-specific wiring (probe + breadcrumbs)                                   | Template / forjd-ui imports                                     |
| Domain / infra | `core/ready/`, `core/fetch/` (`fetch-handle`, `swr-cache`), `core/offline/`, `core/monitoring/`, `core/bootstrap/` | `/ready` contract, fetch phases, SWR cache, online/offline, ops SDKs, idle init | Angular components / suite CSS; no mega multi-key global stores |
| Primitives     | `libs/forjd-ui/`                                                                                                   | Suite UI adapter (a11y, chrome, forms, …)                                       | `environment`, API URLs, `/ready`, auth                         |

## Rules

1. **forjd-ui** never calls backends or reads `environment` DSNs.
2. **Landing** calls `probeLandingReady` / content helpers — it does not implement HTTP.
3. **Monitoring config** is built only via `monitoringConfigFromEnvironment()`; always pass it (no cached config singleton).
4. Prefer **local signals + flat `computed`s** on the component (ADR-0010); keep only justified cross-cutting services (theme, toast, ErrorHandler). Avoid signal-of-object VMs and nested cache entries.
5. Mutations that touch storage/network: use `runOptimistic` (apply → persist → rollback) — never leave UI ahead of a failed write.
6. New API/clients live under `core/<domain>/`, not inside components.
7. Visual suite law stays in `docs/SUITE_UI_UNIFICATION.md` + forjd-ui README.
8. Landing `/ready` must **not** optimistic-ok — only `'checking'` then settled status.
9. Offline is a distinct status (`offline` ≠ `unreachable`); shell stays readable via ngsw (ADR-0009). No offline sealed ingest on forjd.co.
10. Virtual windows use **index lists** (`indicesForWindow`) + `items()[i]` — not `{ item, index }[]` reactive wrappers.
11. Client reads use **`createFetchHandle`** (`core/fetch/`) — phases `idle|loading|success|error`; templates bind loading/error/success consistently (ADR-0011). Soft probes use `runSettled`.
12. Cached reads use **`createSwrCache`** (one instance per resource): hard `invalidate`, soft `markStale`, background revalidate, subscribe for UI `applySettled` (ADR-0012). `/ready` policy is `READY_CACHE_POLICY`.
13. Navigation URLs use **`safeHref` / `safeHttpBase`** (ADR-0013). Never bind raw user/env strings to `href` without the helper; CSRF stays Bearer/`X-API-Key` (no cookie writes).
14. UGC / third-party strings use **`sanitizeDisplayText`** (client) and backend `sanitize_*` / `text_fields` (ADR-0014). Never trust HTML from partners or OSINT APIs.
15. Output encoding is context-specific (ADR-0015): prefer `{{ }}` auto-escape; use **`encodeForHtml`** only for attribute/template sinks; never `[innerHTML]` for UGC. Backend JSON is serializer-safe; PDF uses `encode_pdf_literal`.
16. API fetches use **`apiFetchInit`** (`credentials: 'omit'`); API bases use `safeHttpBase` with `httpsOnlyExceptLoopback` (ADR-0016). No session cookies on forjd.co.
17. Secrets: never put `fjsvc_` in the browser; console/monitoring use **`scrubValue`** (ADR-0017). Backend logs/trackers use `scrub_for_logs`.
18. External JSON: use **`parseResponseJson`** (soft fail on bad JSON). Backend outbound uses `outbound_http` (ADR-0018).
19. Notifications use **`FjToastService`** priority stack (max 3, tone→priority, dedupe, hover-pause) — ADR-0020. Prefer `success()` / `critical()`; do not invent a second snackbar.
20. **Landing app does not mount** prefs sheet, shortcut help, search palette, onboarding checklist, command history, bulk select, or disclosure chrome. Those adapters remain in **forjd-ui** / Storybook for suite parity (ADRs 0019–0027); do not reintroduce them on forjd.co without a product surface that needs them.
21. Theme FOUC stays in `index.html` (`suite-theme` / system). No in-app theme toolbar on the public landing.
22. Loading / ready / degraded / shell failure copy is one product story: `landingReadyStory()` + `SHELL_STORY` — not ad-hoc ops strings.
23. Constrained delivery (`prefersConstrainedDelivery` — Save-Data / `prefers-reduced-data`) skips idle analytics/monitoring and font preload; suite CSS simplifies atmosphere under 600px / reduced-data.

Config inventory: `config/forjd.catalog.yaml` · `docs/CONFIGURATION.md`.
