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

Mobile-first: controls share one tactile grid — `--suite-touch` (44px) by default; desktop densifies to `--suite-control-height` (40px) at `≥768px`. Buttons, inputs, selects, tabs, and nav links use the same `--_control-h` / padding / type scale. Feedback: hover lift + elevation-2 (raised), press sink + inset shadow, fields rest as inset wells.

## Interaction / motion / spacing language (Pass 7)

Every **interactive** primitive must share this contract (buttons are the reference):

| Concern        | Token / pattern                                                                        |
| -------------- | -------------------------------------------------------------------------------------- |
| Transition     | `transition: var(--suite-transition)` (or `-colors` / `-transform`)                    |
| Hover          | `translateY(var(--suite-hover-lift))` + elevation step where raised                    |
| Active / press | `translateY(var(--suite-press-sink))` or inset elevation                               |
| Focus          | `:focus-visible` → `outline: var(--suite-ring-width) solid var(--suite-ring)` + offset |
| Disabled       | `opacity: 0.55`, `cursor: not-allowed`, no hover/active transforms                     |
| Touch          | `min-height: var(--suite-touch)` on mobile; densify at `≥768px`                        |
| Reduced motion | File-end kill-switch zeros transforms/animations                                       |

Surface titles use `.suite-panel-title` / `.viking-panel-title` / `.fj-panel-title` in **suite-components** (not landing-only) so Storybook and product hosts match.

## Class contracts (triple prefix)

Every primitive accepts **any** of these prefixes (same rules):

| Primitive      | Classes                                                       | Variants / notes                                                                                                                               |
| -------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Button         | `.suite-btn` / `.viking-btn` / `.fj-btn`                      | `data-variant`: primary · secondary · outline · ghost · subtle · danger; `data-size`: sm · lg; `data-square`; loading via `.suite-btn-spinner` |
| Link           | `.suite-link` / `.viking-link` / `.fj-link`                   | Text links                                                                                                                                     |
| Field          | `.suite-field` / `.viking-field` / `.fj-field`                | label, description, error                                                                                                                      |
| Input          | `.suite-input` / `.viking-input` / `.fj-input`                | `aria-invalid`                                                                                                                                 |
| Textarea       | `.suite-textarea` / `.viking-textarea` / `.fj-textarea`       |                                                                                                                                                |
| Select         | `.suite-select` / `.viking-select` / `.fj-select`             | custom chevron                                                                                                                                 |
| Checkbox       | `.suite-checkbox` / `.viking-checkbox` / `.fj-checkbox`       | native + accent                                                                                                                                |
| Radio          | `.suite-radio` / `.viking-radio` / `.fj-radio`                |                                                                                                                                                |
| Switch         | `.suite-switch` + `.suite-switch-track`                       | role=switch                                                                                                                                    |
| Card           | `.suite-card` / `.viking-card` / `.fj-card`                   | `data-interactive`, `data-elevated`                                                                                                            |
| Badge          | `.suite-badge`                                                | `data-tone`: accent · success · warning · danger · gold                                                                                        |
| Dialog         | `.suite-dialog` + header/title/body/footer                    | native `<dialog>`                                                                                                                              |
| Search palette | `.suite-search-palette` + backdrop/header/body/footer/results | ⌘K / `/`; ranked filter; recent searches in localStorage                                                                                       |
| Sheet          | `.suite-sheet` + `data-side` left/right                       |                                                                                                                                                |
| Tabs           | `.suite-tabs` · list · tab · panel                            | keyboard tablist                                                                                                                               |
| Table          | `.suite-table-wrap` + `.suite-table`                          | `data-density="compact"`                                                                                                                       |
| Nav            | `.suite-nav` · `.suite-nav-link`                              | `aria-current` / `data-active`                                                                                                                 |
| Toast          | `.suite-toast-host` + `.suite-toast`                          | Priority stack (`data-priority`: low·normal·high·critical); max 3; `data-tone`; hover pauses dismiss                                           |
| Skeleton       | `.suite-skeleton` · `.suite-skeleton-stack`                   | `data-variant`: text · rect · circle; stack = hydrating list/card recipe                                                                       |
| Empty          | `.suite-empty` + icon/eyebrow/title/description/hint/actions  | `data-density="compact"` · `data-variant="inset"`                                                                                              |
| Loading        | `.suite-loading` · `.suite-loading-overlay` + panel           | spinner + title/detail; overlay uses backdrop + machined panel                                                                                 |
| Error state    | `.suite-error-state` + icon/title/description/hint/actions    | recovery panel — not field `.suite-error-text` / `.fj-error`                                                                                   |
| Avatar         | `.suite-avatar`                                               | `data-size`: sm · md · lg                                                                                                                      |
| Separator      | `.suite-separator`                                            | vertical via `data-orientation`                                                                                                                |
| Callout        | `.suite-callout`                                              | `data-tone` (danger stays soft + readable ink)                                                                                                 |
| Progress       | `.suite-progress` + `.suite-progress-bar`                     | `--_progress` width                                                                                                                            |
| Spinner        | `.suite-spinner`                                              | `data-size="lg"`                                                                                                                               |
| Theme toggle   | `.suite-theme-toggle` / `.theme-toggle-btn`                   | pairs with `suite-theme` storage + `data-theme` on `<html>`                                                                                    |
| Status list    | `.suite-status-list`                                          | `data-ok` on items                                                                                                                             |
| Pipeline flow  | `.suite-pipeline-flow`                                        | read-only workflow steps; `data-orientation` + `data-kind` on steps                                                                            |
| Stream status  | `.suite-stream-status`                                        | near-real-time chip; `data-phase` / `data-tone`; pulse only when connected                                                                     |
| Page shell     | `.suite-page-shell` · section · stack                         | stack modifiers `--tight/compact/loose/center`                                                                                                 |

## Angular selectors (matched APIs)

| forjd-ui                                     | viking-ui                                    | Notes                                                                              |
| -------------------------------------------- | -------------------------------------------- | ---------------------------------------------------------------------------------- |
| `forjd-button`                               | `viking-button`                              | variants aligned; filled→primary, subtle→ghost                                     |
| `forjd-input`                                | `viking-input`                               | CVA                                                                                |
| `forjd-textarea`                             | `viking-textarea`                            | CVA                                                                                |
| `forjd-select`                               | `viking-native-select` / select              | options input                                                                      |
| `forjd-checkbox`                             | `viking-checkbox`                            | CVA                                                                                |
| `forjd-switch`                               | `viking-toggle` / switch                     | CVA + track                                                                        |
| `forjd-card` / `forjd-panel`                 | `viking-card`                                | panel = section + card                                                             |
| `forjd-badge`                                | `viking-badge`                               | tone                                                                               |
| `forjd-dialog` / `forjd-sheet`               | `viking-modal` / `viking-sheet`              | native `<dialog>`                                                                  |
| `forjd-search-palette`                       | `viking-command-palette` / suite             | ⌘K / `/`, ranked results, recent searches                                          |
| `forjd-tabs`                                 | `viking-tabs`                                | keyboard tablist                                                                   |
| `forjd-table`                                | `viking-table`                               | dense data + optional multi-select (ADR-0021)                                      |
| `forjd-bulk-toolbar`                         | `viking-bulk-toolbar`                        | non-modal bulk actions when rows selected                                          |
| `createSelectionModel`                       | `createSelectionModel`                       | stable-id multi-select helper                                                      |
| `forjd-disclosure`                           | `viking-disclosure`                          | progressive disclosure; advanced collapsed (ADR-0022)                              |
| `createDisclosureStore`                      | `createDisclosureStore`                      | smart defaults + `suite-disclosure-v1` persist                                     |
| `forjd-shortcut-help`                        | `viking-shortcut-help`                       | `?` opens shortcut reference (ADR-0023)                                            |
| `createShortcutRegistry`                     | `createShortcutRegistry`                     | suite shortcut catalog + format helpers                                            |
| `forjd-preferences`                          | `viking-preferences`                         | prefs sheet/modal; ⌘, (ADR-0024)                                                   |
| `createPreferencesStore`                     | `createPreferencesStore`                     | `suite-preferences-v1` persist + tab sync                                          |
| `exportSuiteDataPack` / `applySuiteDataPack` | same                                         | soft chrome JSON pack; merge/replace (ADR-0026)                                    |
| `forjd-activity-list`                        | `viking-activity-list`                       | recent soft-chrome actions (ADR-0027)                                              |
| `forjd-pipeline-flow`                        | `viking-pipeline-flow`                       | read-only workflow YAML steps (visual cards)                                       |
| `forjd-stream-status`                        | `viking-stream-status`                       | calm near-real-time chip (never “Live”)                                            |
| `createActivityLog`                          | `createActivityLog`                          | capped local `suite-activity-v1`; never secrets                                    |
| `forjd-onboarding-checklist`                 | `viking-onboarding-checklist`                | first-time guide; `suite-onboarding-v1` (ADR-0025)                                 |
| `createOnboardingStore`                      | `createOnboardingStore`                      | dismiss / complete / step ids + tab sync                                           |
| `forjd-toast-host` + service                 | `viking-toast`                               | host + items                                                                       |
| `forjd-skeleton`                             | `viking-skeleton`                            |                                                                                    |
| `forjd-empty`                                | `viking-empty-state`                         | icon · hint · eyebrow · density; use `SUITE_EMPTY_GUIDANCE_EYEBROW` for first-time |
| `forjd-loading` / `forjd-loading-overlay`    | `viking-loading-overlay`                     | inline panel vs overlay                                                            |
| `forjd-error-state`                          | `viking-error-state`                         | recovery actions via projection                                                    |
| `forjd-theme-toggle` + `FjThemeService`      | `viking-theme-toggle` + `VikingThemeService` | system + persist                                                                   |
| `forjd-avatar`                               | `viking-avatar`                              |                                                                                    |
| `forjd-separator`                            | `viking-separator`                           |                                                                                    |
| `forjd-nav`                                  | site navbar links                            |                                                                                    |
| `forjd-page-shell` / section / stack         | layout shells                                |                                                                                    |

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

## Focus + keyboard (suite-wide)

| Concern           | Contract                                                                           |
| ----------------- | ---------------------------------------------------------------------------------- |
| Ring              | `--suite-ring` · `--suite-ring-width` · `--suite-ring-offset` via `:focus-visible` |
| Skip link         | `.suite-skip-link` / `.skip-link` → `#main-content` (`tabindex="-1"` on `<main>`)  |
| Overlays          | Native `<dialog showModal>` traps Tab; restore focus to opener on close            |
| Tabs / nav        | Roving tabindex — Arrow / Home / End; helpers in `core/focus` / `forjd-ui` a11y    |
| Mouse vs keyboard | `:focus:not(:focus-visible) { outline: none }` on buttons/links/tabs               |
| Forced colors     | 3px `CanvasText` outline                                                           |

```html
<a href="#main-content" class="suite-skip-link skip-link"
  >Skip to main content</a
>
<main id="main-content" class="suite-main" tabindex="-1">…</main>
```

## Rules

1. **No hard-coded colors** in component chrome — only `var(--suite-*)` (or aliases that resolve to suite).
2. **Touch targets ≥ `--suite-touch` (44px)** on interactive controls (desktop may densify via `--suite-control-height*`).
3. **Tactile feedback is shared:** hover → `--suite-hover-lift` + elevation step; active → `--suite-press-sink` + `--suite-elevation-inset`; fields use inset wells + `--suite-control-focus-ring`.
4. **`:focus-visible`** provided globally for listed controls; do not remove or restyle with a second ring system.
5. **Apps compose, do not restyle** primitives. Extend suite-components.css first.
6. **Prefer `data-variant` / `data-tone` / `data-size`** over one-off class forks (inputs accept `data-size` sm/lg to match buttons).
7. **Accessibility (WCAG 2.2 AA):** native dialog + Tab trap + focus restore, switch `role="switch"`, tablist/tab/tabpanel, toast `aria-live`, disabled/aria-disabled, `html` scroll-padding for sticky chrome, touch targets ≥ `--suite-touch` (44px).

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

## Reduced motion (WCAG 2.3.3)

`suite-tokens.css` zeros motion tokens under `prefers-reduced-motion: reduce`.
`suite-components.css` also applies a suite-wide kill-switch (animation/transition
durations, `scroll-behavior: auto`) so FORJD surfaces that load suite CSS only
match DEML. Prefer tokenized motion; never invent alternate timings for reduced
motion — disable or snap.

## Verify

```bash
# DEML
node packages/viking-ui/scripts/check-suite-components.mjs
npm run suite:purity

# FORJD
cd frontend && npm run sync:suite
# suite-components.css SHA must match DEML
```
