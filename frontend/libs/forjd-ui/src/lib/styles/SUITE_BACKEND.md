# Suite backend — Pass 4

**Styles:** [`suite-backend.css`](./suite-backend.css)
**Depends on:** [`suite-tokens.css`](./suite-tokens.css), [`suite-components.css`](./suite-components.css)

## Goal

`backend.forjd.co` and `backend.deml.app` are the **operational twin** of the product frontends: same tokens and component chrome, quieter and more focused. Logo splash is perfectly centered. Docs shells share one thin topbar.

## Class contracts

| Role         | Classes                                                               |
| ------------ | --------------------------------------------------------------------- |
| Splash body  | `.suite-backend-splash` / `body.backend-splash`                       |
| Splash shell | `.suite-backend-shell` / `.backend-splash-shell`                      |
| Logo link    | `.suite-backend-logo` / `.backend-splash-logo`                        |
| Docs body    | `.suite-backend-docs` / `body.backend-swagger` / `body.backend-redoc` |
| Docs topbar  | `.suite-backend-topbar` / `.backend-docs-topbar` / `.fj-topbar`       |
| Brand mark   | `.suite-backend-brand` / `.backend-docs-brand` / `.fj-brand`          |

## Load order

```
suite-tokens.css → suite-components.css → suite-backend.css
```

FORJD: vendored via `npm run sync:suite` into `backend/static/`.
DEML: folded into `viking-ui.css` via `build-css.mjs` (no separate `<link>` required when using the full bundle).

## Rules

1. No inline product hex or one-off splash CSS in app templates.
2. Splash is logo-only — no stats, CTAs, or cards on `/`.
3. Topbar nav links use suite mono + muted ink; primary accent on brand only.
