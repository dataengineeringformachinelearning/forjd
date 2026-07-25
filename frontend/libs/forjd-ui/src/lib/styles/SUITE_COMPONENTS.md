# Suite components — Pass 2

**Styles:** [`suite-components.css`](./suite-components.css) (owned; `--suite-*` tokens only)
**Tokens:** [`suite-tokens.css`](./suite-tokens.css)

## Goal

Identical chrome whether the host is deml.app, forjd.co, backend landings, or Storybook.
Headless / light Angular behavior + owned CSS. No Material / Bootstrap / shadcn runtime themes.

## Class contracts

Every primitive accepts **any** of these prefixes (same rules):

| Role                         | Classes                                                                       |
| ---------------------------- | ----------------------------------------------------------------------------- |
| Button                       | `.suite-btn` / `.viking-btn` / `.fj-btn` + `data-variant` or `.*-btn-primary` |
| Input                        | `.suite-input` / `.viking-input` / `.fj-input`                                |
| Textarea                     | `.suite-textarea` / `.fj-textarea`                                            |
| Select                       | `.suite-select` / `.fj-select`                                                |
| Checkbox                     | `.suite-checkbox` / `.fj-checkbox`                                            |
| Switch                       | `.suite-switch` / `.fj-switch`                                                |
| Card                         | `.suite-card` / `.viking-card` / `.fj-card`                                   |
| Badge                        | `.suite-badge` / `.viking-badge` / `.fj-badge`                                |
| Tabs                         | `.suite-tabs` / `.fj-tabs` (+ list, tab, panel)                               |
| Dialog / Sheet               | `.suite-dialog` / `.fj-dialog`, `.suite-sheet` / `.fj-sheet`                  |
| Table                        | `.suite-table-wrap` + `.suite-table`                                          |
| Toast                        | `.suite-toast-host` + `.suite-toast`                                          |
| Skeleton / Empty             | `.suite-skeleton`, `.suite-empty`                                             |
| Nav / Avatar / Separator     | `.suite-nav-link`, `.suite-avatar`, `.suite-separator`                        |
| Callout heading              | `.suite-callout-heading` / `.fj-callout-heading`                              |
| Status list                  | `.suite-status-list` / `.fj-status-list`                                      |
| Page shell / section / stack | `.suite-page-shell`, `.suite-section`, `.suite-stack` (+ `.fj-*`)             |

## Angular selectors (matched APIs)

| forjd-ui                       | viking-ui                       | Notes                                                |
| ------------------------------ | ------------------------------- | ---------------------------------------------------- |
| `forjd-button`                 | `viking-button`                 | variants: primary, secondary, outline, danger, ghost |
| `forjd-input`                  | `viking-input`                  | CVA                                                  |
| `forjd-textarea`               | `viking-textarea`               | CVA                                                  |
| `forjd-select`                 | `viking-native-select` / select | options input                                        |
| `forjd-checkbox`               | `viking-checkbox`               | CVA                                                  |
| `forjd-switch`                 | `viking-toggle`                 | CVA                                                  |
| `forjd-card` / `forjd-panel`   | `viking-card`                   | panel keeps section+card                             |
| `forjd-badge`                  | `viking-badge`                  | tone                                                 |
| `forjd-dialog` / `forjd-sheet` | `viking-modal` / `viking-sheet` | native `<dialog>`                                    |
| `forjd-tabs`                   | `viking-tabs`                   | keyboard tablist                                     |
| `forjd-table`                  | `viking-table`                  | dense data                                           |
| `forjd-toast`                  | `viking-toast`                  | host + items                                         |
| `forjd-skeleton`               | `viking-skeleton`               |                                                      |
| `forjd-empty`                  | `viking-empty-state`            |                                                      |
| `forjd-avatar`                 | `viking-avatar`                 |                                                      |
| `forjd-separator`              | —                               | hr                                                   |
| `forjd-nav`                    | site navbar links               |                                                      |

## Load order

```html
<link rel="stylesheet" href="suite-tokens.css" />
<link rel="stylesheet" href="suite-components.css" />
```

FORJD: `npm run sync:suite` vendors both files.
DEML: included in `design-tokens` / package build via `build-css.mjs`.

## Rules

1. No hard-coded colors in component SCSS — only `var(--suite-*)` (or aliases).
2. Touch targets ≥ `--suite-touch` (44px).
3. Always define `:focus-visible` (provided globally for listed controls).
4. Prefer composition; apps should not restyle primitives.
