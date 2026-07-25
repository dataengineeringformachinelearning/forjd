# Suite tokens — usage

**Canonical file:** [`suite-tokens.css`](./suite-tokens.css)
**Built artifact:** `packages/viking-ui/dist/suite-tokens.css`
**Vendored into FORJD:** `frontend/libs/forjd-ui/src/lib/styles/suite-tokens.css` (no npm install for styles)

## Strategy

| Choice        | Decision                                                               |
| ------------- | ---------------------------------------------------------------------- |
| Default theme | **Dark-first** void austerity (`#0a0a0a` surfaces)                     |
| Light         | Opt-in only: `<html data-theme="light">` — lightness shift, same roles |
| Primary       | Electric `#2176ff` (DEML)                                              |
| Gold          | Institutional `#d4af37` (FORJD)                                        |
| Brand artwork | `--suite-brand-navy` / `--suite-brand-blue` — logos only               |

## Prefixes

| Prefix       | Role                                 |
| ------------ | ------------------------------------ |
| `--suite-*`  | **Canonical** — use in new code      |
| `--viking-*` | Alias → suite (viking-ui / deml.app) |
| `--fj-*`     | Alias → suite (forjd-ui / forjd.co)  |

All three resolve to the same computed values. Never invent parallel hexes.

## Load order

```html
<link rel="stylesheet" href="/path/to/suite-tokens.css" />
<!-- then components / app styles that only use var(--suite-*) or aliases -->
```

**DEML:** included in `design-tokens.css` build; sync via `python scripts/sync_design_system.py`.
**FORJD:** import the vendored file from forjd-ui (see below). Refresh with sibling checkout:

```bash
# from forjd/frontend
npm run sync:suite
```

## Usage examples

```css
.panel {
  background: var(--suite-surface);
  border: 1px solid var(--suite-border);
  border-radius: var(--suite-radius-lg);
  padding: var(--suite-space-3);
  color: var(--suite-ink);
  box-shadow: var(--suite-shadow-sm);
}

.cta {
  background: var(--suite-primary);
  color: var(--suite-ink-on-primary);
  min-height: var(--suite-touch);
  transition: var(--suite-transition);
}

.cta:focus-visible {
  outline: var(--suite-ring-width) solid var(--suite-ring);
  outline-offset: var(--suite-ring-offset);
}
```

FORJD / Viking aliases (identical):

```css
/* either works */
color: var(--suite-ink);
color: var(--viking-text);
color: var(--fj-text);
```

## Rules

1. **No hard-coded colors** outside `suite-tokens.css` (exception: brand SVG assets).
2. **No magic spacing/radius** — use `--suite-space-*` / `--suite-radius-*`.
3. **Components own look via tokens** — apps compose; they do not redefine chrome.
4. Edit the canonical file in DEML first, rebuild/sync, then vendor into FORJD.

## Role cheat sheet

| Need                       | Token                                        |
| -------------------------- | -------------------------------------------- |
| Page background            | `--suite-bg`                                 |
| Card / panel               | `--suite-surface`                            |
| Nested well                | `--suite-surface-2`                          |
| Raised control             | `--suite-surface-elevated`                   |
| Body text                  | `--suite-ink`                                |
| Secondary text             | `--suite-ink-muted`                          |
| Border                     | `--suite-border`                             |
| CTA / link                 | `--suite-primary`                            |
| Institutional accent       | `--suite-gold`                               |
| Danger / success / warning | `--suite-danger` / `--success` / `--warning` |
| Sans / mono                | `--suite-font-sans` / `--suite-font-mono`    |
| Control height             | `--suite-touch`                              |
