# Suite docs — Pass 5

**Styles:** [`suite-docs.css`](./suite-docs.css)
**Hosts:** [ui.deml.app](https://ui.deml.app) · [ui.forjd.co](https://ui.forjd.co)
**Gate:** `node packages/viking-ui/scripts/check-suite-docs.mjs` (via `suite:purity`)

## Goal

Both Storybooks **demonstrate the unified system**:

| Layer    | Contract                                                                                         |
| -------- | ------------------------------------------------------------------------------------------------ |
| Manager  | Dark void + electric accent; brand title only differs (`Suite UI · Viking` / `Suite UI · FORJD`) |
| Canvas   | Same void backgrounds (`--suite-bg` / surface / elevated)                                        |
| Frame    | `.suite-story-shell` + `.suite-story-panel` (triple-classed with viking/fj)                      |
| Styles   | suite-fonts → suite-tokens → suite-components → **suite-docs**                                   |
| Taxonomy | `Foundation/*` · `Primitives/*` · `Product/*` (DEML depth only under Product)                    |

A designer flipping between ui.deml.app and ui.forjd.co should see the **same chrome DNA** on shared primitives (Button, Forms, Badge, Overlay, Surface, …).

## Load order (Storybook only)

```
suite-fonts.css
suite-tokens.css
suite-components.css
suite-docs.css
(+ DEML: design-tokens + viking-ui for Product/* WC depth)
```

Do **not** load `suite-docs.css` into product apps, marketing, or backend shells.

## Story frame

```html
<div
  class="suite-story-shell viking-story-shell fj-story-shell"
  data-theme="dark"
>
  <div
    class="suite-story-panel viking-story-panel fj-story-panel"
    data-size="compact"
  >
    <!-- story -->
  </div>
</div>
```

| Class                                   | Role                                      |
| --------------------------------------- | ----------------------------------------- |
| `.suite-story-shell`                    | Full-bleed void stage (atmosphere + grid) |
| `.suite-story-panel`                    | Machined product surface for the demo     |
| `[data-size="compact"]`                 | Tighter panel for primitives              |
| `[data-bleed="true"]`                   | Full-bleed charts / mockups               |
| `.suite-story-row` / `.grid` / `.stack` | Layout helpers                            |
| `.suite-story-kicker`                   | Mono section label                        |
| `.suite-story-metric*`                  | Foundation metric tiles                   |

## Manager branding

| Host        | brandTitle          | Palette                            |
| ----------- | ------------------- | ---------------------------------- |
| ui.deml.app | `Suite UI · Viking` | void `#0a0a0a`, electric `#2176ff` |
| ui.forjd.co | `Suite UI · FORJD`  | **identical**                      |

## Shared primitives (must match visually)

`Foundation/Tokens`, `Foundation/Typography`,
`Primitives/Button`, `Badge`, `Callout`, `Card`/`Surface`, `Field`/`Forms`, `Input`, `Overlay`, `PageShell` (FORJD) / layout adapters.

`Product/*` remains DEML-only depth (status cards, suite header, charts, …) but still uses suite tokens + story chrome.

## FORJD vendor

```bash
cd forjd/frontend && npm run sync:suite
# suite-docs.css → libs/forjd-ui/src/lib/styles/
```

## Verify

```bash
npm run suite:docs
npm run suite:purity

# Storybook builds
cd packages/viking-ui && npm run build-storybook
cd forjd/frontend && npm run build-storybook
```
