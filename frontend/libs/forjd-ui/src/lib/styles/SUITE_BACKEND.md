# Suite backend — Pass 4

**Styles:** [`suite-backend.css`](./suite-backend.css)
**Depends on:** [`suite-tokens.css`](./suite-tokens.css), [`suite-components.css`](./suite-components.css), [`suite-fonts.css`](./suite-fonts.css)
**Gate:** `node packages/viking-ui/scripts/check-suite-backend.mjs` (via `suite:purity`)

## Goal

`backend.forjd.co` and `backend.deml.app` are the **operational twin** of the product frontends:

| Trait  | Rule                                                               |
| ------ | ------------------------------------------------------------------ |
| Logo   | **Perfectly centered** (flex + place-items center, full viewport)  |
| Layout | Quiet vertical shell — logo only on `/`                            |
| Chrome | Thin sticky docs topbar for Swagger / ReDoc                        |
| Type   | Self-hosted Inter via suite-fonts                                  |
| Color  | Void `#0a0a0a` + electric brand only — no cyan, no marketing bands |
| Load   | Minimal CSS (suite-fonts → tokens → components → backend)          |

Same design system as forjd.co / deml.app — **quieter and more focused**.

## Class contracts

| Role              | Classes                                                               |
| ----------------- | --------------------------------------------------------------------- |
| Splash body       | `.suite-backend-splash` / `body.backend-splash`                       |
| Splash shell      | `.suite-backend-shell` / `.backend-splash-shell`                      |
| Logo link         | `.suite-backend-logo` / `.backend-splash-logo`                        |
| Optional wordmark | `.suite-backend-wordmark`                                             |
| Docs body         | `.suite-backend-docs` / `body.backend-swagger` / `body.backend-redoc` |
| Docs topbar       | `.suite-backend-topbar` / `.backend-docs-topbar` / `.fj-topbar`       |
| Brand mark        | `.suite-backend-brand` / `.backend-docs-brand` / `.fj-brand`          |

## Markup (splash)

```html
<html lang="en" data-theme="dark">
  <head>
    <meta name="theme-color" content="#0a0a0a" />
    <link rel="stylesheet" href="/static/suite-fonts.css" />
    <link rel="stylesheet" href="/static/suite-tokens.css" />
    <link rel="stylesheet" href="/static/suite-components.css" />
    <link rel="stylesheet" href="/static/suite-backend.css" />
    <!-- DEML: viking-ui.css already includes suite stages -->
  </head>
  <body class="suite-backend-splash backend-splash">
    <main class="suite-backend-shell backend-splash-shell">
      <a
        class="suite-backend-logo backend-splash-logo"
        href="https://forjd.co/"
      >
        <img src="/static/forjd.svg" width="270" height="270" alt="FORJD" />
      </a>
    </main>
  </body>
</html>
```

## Markup (docs topbar)

```html
<body class="suite-backend-docs backend-swagger">
  <header class="suite-backend-topbar backend-docs-topbar fj-topbar">
    <a class="suite-backend-brand" href="https://forjd.co/">FORJD</a>
    <nav aria-label="API documentation">
      <a href="…">product</a>
      <a href="/redoc">redoc</a>
      …
    </nav>
  </header>
  <div id="swagger-ui"></div>
</body>
```

## Load order

```
suite-fonts → suite-tokens → suite-components → suite-backend
```

| Host             | Delivery                                                                                 |
| ---------------- | ---------------------------------------------------------------------------------------- |
| backend.forjd.co | `/static/suite-*.css` vendored by `npm run sync:suite` (fonts at `/static/fonts/inter/`) |
| backend.deml.app | `viking-ui.css` (suite bundle folded in via `build-css.mjs`)                             |

## Rules

1. **No inline product hex** or one-off splash CSS in app templates (no `#00b4ff`).
2. **Splash is logo-only** — no stats, CTAs, cards, or marketing sections on `/`.
3. **Topbar** uses mono uppercase muted links; primary accent on brand only.
4. **Swagger method chips** stay quiet (surface-2), not multicolored rainbow.
5. **theme-color** is `#0a0a0a` (void lockstep).

## Verify

```bash
npm run suite:backend
npm run suite:purity

# FORJD
cd frontend && npm run sync:suite
curl -sS https://backend.forjd.co/ | grep -E 'suite-backend|suite-fonts'
curl -sS -o /dev/null -w "%{http_code}\n" https://backend.forjd.co/static/fonts/inter/InterVariable.woff2

# DEML
curl -sS https://backend.deml.app/ | grep -E 'suite-backend|backend-splash'
```
