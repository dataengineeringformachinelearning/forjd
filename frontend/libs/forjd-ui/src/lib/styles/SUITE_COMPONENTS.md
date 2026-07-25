# Suite components — Pass 2

**Styles:** [`suite-components.css`](./suite-components.css) (owned; `--suite-*` tokens only)
**Tokens:** [`suite-tokens.css`](./suite-tokens.css) (Pass 1)
**Gate:** `node packages/viking-ui/scripts/check-suite-components.mjs` (also via `suite:purity`)

## Goal

Identical chrome whether the host is deml.app, forjd.co, backend landings, marketing, or Storybook.
**Headless behavior + owned CSS.** No Material / Bootstrap / Blueprint / shadcn / Spartan runtime themes.

A developer should compose suite classes (or `forjd-*` / `viking-*` Angular adapters) and get the **exact same look** with zero extra styling work.

## Aesthetic contract

| Inspiration             | How it shows up                                                             |
| ----------------------- | --------------------------------------------------------------------------- |
| SpaceX                  | Void surfaces, sparse hierarchy, severe geometry                            |
| Palantir                | Dense tables (`data-density="compact"`), mono nav, operational status lists |
| Porsche                 | Tight radii, hairline highlights, precise hover/active                      |
| Spartan / Flux / shadcn | Composable class contracts, variants via `data-*`                           |

Mobile-first: controls use `--suite-touch` (44px) by default; desktop may densify to `--suite-control-height` (40px) at `≥768px`.

## Class contracts (triple prefix)

Every primitive accepts **any** of these prefixes (same rules):

| Primitive   | Classes                                                 | Variants / notes                                                                                                                               |
| ----------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Button      | `.suite-btn` / `.viking-btn` / `.fj-btn`                | `data-variant`: primary · secondary · outline · ghost · subtle · danger; `data-size`: sm · lg; `data-square`; loading via `.suite-btn-spinner` |
| Link        | `.suite-link` / `.viking-link` / `.fj-link`             | Text links                                                                                                                                     |
| Field       | `.suite-field` / `.viking-field` / `.fj-field`          | label, description, error                                                                                                                      |
| Input       | `.suite-input` / `.viking-input` / `.fj-input`          | `aria-invalid`                                                                                                                                 |
| Textarea    | `.suite-textarea` / `.viking-textarea` / `.fj-textarea` |                                                                                                                                                |
| Select      | `.suite-select` / `.viking-select` / `.fj-select`       | custom chevron                                                                                                                                 |
| Checkbox    | `.suite-checkbox` / `.viking-checkbox` / `.fj-checkbox` | native + accent                                                                                                                                |
| Radio       | `.suite-radio` / `.viking-radio` / `.fj-radio`          |                                                                                                                                                |
| Switch      | `.suite-switch` + `.suite-switch-track`                 | role=switch                                                                                                                                    |
| Card        | `.suite-card` / `.viking-card` / `.fj-card`             | `data-interactive`, `data-elevated`                                                                                                            |
| Badge       | `.suite-badge`                                          | `data-tone`: accent · success · warning · danger · gold                                                                                        |
| Dialog      | `.suite-dialog` + header/title/body/footer              | native `<dialog>`                                                                                                                              |
| Sheet       | `.suite-sheet` + `data-side` left/right                 |                                                                                                                                                |
| Tabs        | `.suite-tabs` · list · tab · panel                      | keyboard tablist                                                                                                                               |
| Table       | `.suite-table-wrap` + `.suite-table`                    | `data-density="compact"`                                                                                                                       |
| Nav         | `.suite-nav` · `.suite-nav-link`                        | `aria-current` / `data-active`                                                                                                                 |
| Toast       | `.suite-toast-host` + `.suite-toast`                    | Sonner-style; `data-tone`; `data-position`                                                                                                     |
| Skeleton    | `.suite-skeleton`                                       | `data-variant`: text · rect · circle                                                                                                           |
| Empty       | `.suite-empty` + title/description/actions              |                                                                                                                                                |
| Avatar      | `.suite-avatar`                                         | `data-size`: sm · md · lg                                                                                                                      |
| Separator   | `.suite-separator`                                      | vertical via `data-orientation`                                                                                                                |
| Callout     | `.suite-callout`                                        | `data-tone`                                                                                                                                    |
| Progress    | `.suite-progress` + `.suite-progress-bar`               | `--_progress` width                                                                                                                            |
| Spinner     | `.suite-spinner`                                        |                                                                                                                                                |
| Status list | `.suite-status-list`                                    | `data-ok` on items                                                                                                                             |
| Page shell  | `.suite-page-shell` · section · stack                   | stack modifiers `--tight/compact/loose/center`                                                                                                 |

## Angular selectors (matched APIs)

| forjd-ui                             | viking-ui                       | Notes                                          |
| ------------------------------------ | ------------------------------- | ---------------------------------------------- |
| `forjd-button`                       | `viking-button`                 | variants aligned; filled→primary, subtle→ghost |
| `forjd-input`                        | `viking-input`                  | CVA                                            |
| `forjd-textarea`                     | `viking-textarea`               | CVA                                            |
| `forjd-select`                       | `viking-native-select` / select | options input                                  |
| `forjd-checkbox`                     | `viking-checkbox`               | CVA                                            |
| `forjd-switch`                       | `viking-toggle` / switch        | CVA + track                                    |
| `forjd-card` / `forjd-panel`         | `viking-card`                   | panel = section + card                         |
| `forjd-badge`                        | `viking-badge`                  | tone                                           |
| `forjd-dialog` / `forjd-sheet`       | `viking-modal` / `viking-sheet` | native `<dialog>`                              |
| `forjd-tabs`                         | `viking-tabs`                   | keyboard tablist                               |
| `forjd-table`                        | `viking-table`                  | dense data                                     |
| `forjd-toast-host` + service         | `viking-toast`                  | host + items                                   |
| `forjd-skeleton`                     | `viking-skeleton`               |                                                |
| `forjd-empty`                        | `viking-empty-state`            |                                                |
| `forjd-avatar`                       | `viking-avatar`                 |                                                |
| `forjd-separator`                    | `viking-separator`              |                                                |
| `forjd-nav`                          | site navbar links               |                                                |
| `forjd-page-shell` / section / stack | layout shells                   |                                                |

Adapters apply **triple classes** (`suite-*` + product prefix + peer alias) so CSS matches regardless of which library authored the markup.

## Load order

```html
<link rel="stylesheet" href="suite-tokens.css" />
<link rel="stylesheet" href="suite-components.css" />
<!-- then suite-landing / suite-backend / app composition only -->
```

| Host                         | How styles arrive                                          |
| ---------------------------- | ---------------------------------------------------------- |
| deml.app                     | `viking-app.css` (suite tokens + components folded in)     |
| marketing / backend.deml.app | `viking-ui.css`                                            |
| forjd.co / ui.forjd.co       | forjd-ui styles array: suite-tokens → suite-components → … |
| backend.forjd.co             | `/static/suite-tokens.css` + `suite-components.css`        |

**FORJD vendor (no npm style package):**

```bash
cd forjd/frontend && npm run sync:suite
```

## Rules

1. **No hard-coded colors** in component chrome — only `var(--suite-*)` (or aliases that resolve to suite).
2. **Touch targets ≥ `--suite-touch` (44px)** on interactive controls (desktop may densify).
3. **`:focus-visible`** provided globally for listed controls; do not remove.
4. **Apps compose, do not restyle** primitives. Extend suite-components.css first.
5. **Prefer `data-variant` / `data-tone` / `data-size`** over one-off class forks.
6. **Accessibility:** native dialog, switch `role="switch"`, tablist/tab/tabpanel, toast `aria-live`, disabled/aria-disabled.

## Markup examples

```html
<button
  class="suite-btn fj-btn viking-btn"
  data-variant="primary"
  type="button"
>
  Deploy
</button>

<label class="suite-field fj-field viking-field">
  <span class="suite-label">Email</span>
  <input class="suite-input fj-input viking-input" type="email" />
</label>

<div class="suite-card fj-card viking-card" data-elevated="true">…</div>

<div class="suite-table-wrap">
  <table class="suite-table" data-density="compact">
    …
  </table>
</div>
```

```html
<!-- Angular -->
<forjd-button variant="primary">Deploy</forjd-button>
<viking-button variant="primary">Deploy</viking-button>
<!-- same suite-btn chrome -->
```

## Verify

```bash
# DEML
node packages/viking-ui/scripts/check-suite-components.mjs
npm run suite:purity

# FORJD
cd frontend && npm run sync:suite
# suite-components.css SHA must match DEML
```
