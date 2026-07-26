# forjd-ui layout

Suite adapter for FORJD. Visual SoT remains DEML Viking-UI (`npm run sync:suite`).
ADR: `docs/adr/0006-landing-layers-suite-adapter.md` (adapter, not a second design system).

## Documentation map

| Doc                                                          | Use when                                   |
| ------------------------------------------------------------ | ------------------------------------------ |
| [`COMPONENTS.md`](../../COMPONENTS.md)                       | Props, outputs, composition recipes        |
| [`styles/SUITE_COMPONENTS.md`](./styles/SUITE_COMPONENTS.md) | CSS class variants + Viking selector twins |
| [`styles/SUITE_DOCS.md`](./styles/SUITE_DOCS.md)             | Storybook frame taxonomy                   |
| Storybook autodocs                                           | Interactive knobs (`npm run storybook`)    |

API source of truth for agents: **COMPONENTS.md** + TypeScript signal props on each component. Do not deep-import `lib/`.

## Feature groups

| Group       | Owns                                                                                                         | May import                  |
| ----------- | ------------------------------------------------------------------------------------------------------------ | --------------------------- |
| `core/`     | Framework-neutral a11y + theme helpers (`NativeDialogSession`, `createToastStore`, `forjdUid`, roving/focus) | nothing under other groups  |
| `chrome/`   | Angular theme service / toggle                                                                               | `core/`                     |
| `forms/`    | Buttons + field controls                                                                                     | `core/`                     |
| `overlay/`  | Dialog, sheet, toast                                                                                         | `core/`, `forms/`           |
| `feedback/` | Badge, callout, empty/loading/skeleton, error-state, error-boundary                                          | `core/`, `forms/` (stories) |
| `data/`     | Table, tabs, virtual list, status list                                                                       | `core/`, `feedback/`        |
| `layout/`   | Page shell, nav, card, panel, avatar                                                                         | `core/`                     |
| `styles/`   | Vendored suite CSS — **do not relocate**                                                                     | n/a                         |

## Naming

| Kind             | Convention                             | Example                                                                                                        |
| ---------------- | -------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Selector         | `forjd-*` kebab                        | `forjd-button`, `forjd-dialog`                                                                                 |
| Class            | `Fj*` Pascal                           | `FjButton`, `FjDialog`                                                                                         |
| Types            | `Fj*` Pascal                           | `FjTone`, `FjTableRow`                                                                                         |
| Pure helpers     | camelCase (suite-shared names OK)      | `forjdUid`, `NativeDialogSession`, `runOptimistic`, `createCommandHistory`, `computeVirtualWindow`, `safeHref` |
| Fetch phases     | App `core/fetch` (not forjd-ui)        | `createFetchHandle` → bind `loading` / `error` inputs on data/feedback                                         |
| Navigation       | `safeHref` on every painted `href`     | Block `javascript:` / `data:` / `//…`; `_blank` → `noopener noreferrer`                                        |
| Files            | kebab folder + matching file           | `forms/button/button.ts`, `core/a11y/field-a11y.ts`                                                            |
| Angular services | `*.service.ts`                         | `chrome/theme/theme.service.ts`                                                                                |
| Specs / stories  | colocated `*.spec.ts` / `*.stories.ts` | group-level stories OK for compositions                                                                        |

Dual-adapter vocabulary (intentional — do not force rename):

| Concern         | forjd-ui                    | viking-ui                      |
| --------------- | --------------------------- | ------------------------------ |
| Dialog          | `FjDialog` / `forjd-dialog` | `VikingModal` / `viking-modal` |
| Toast host      | `FjToastHost`               | `VikingToaster`                |
| Empty           | `FjEmpty`                   | `VikingEmptyState`             |
| Field a11y file | `core/a11y/field-a11y.ts`   | `src/core/field-a11y.ts`       |
| UID             | `forjdUid`                  | `vikingUid`                    |

## Import organization

Inside a forjd-ui source file, order imports in blocks separated by a blank line:

1. Angular / framework (`@angular/*`)
2. Third-party (`@storybook/*`, `vitest`, …)
3. Cross-group relatives (`../../core/…`, `../forms/…`)
4. Same-folder / local (`./tones`, `./button`)

Rules:

- Prefer `import type` for type-only symbols.
- Import `forjdUid` from `core/a11y/uid` (not from field-a11y).
- App code imports **only** from `forjd-ui` / `public-api.ts` — never deep `lib/` paths.
- `core/` must not import feature groups (forms/overlay/…). Integration specs that need components live under the feature group (e.g. `forms/field/field.spec.ts`).

## Boundaries

1. App code imports **only** from `forjd-ui` / `public-api.ts` — never deep paths into `lib/`.
2. New primitives land under the matching group: `lib/<group>/<name>/`.
3. Colocate `*.stories.ts` / `*.spec.ts` with the component (group-level stories OK for compositions).
4. Keep `styles/` path stable — sync + purity scripts lock it.
5. No per-group `index.ts` barrels — `public-api.ts` is the only library barrel.

## Adding a component

1. Create `lib/<group>/<name>/<name>.ts` (+ story).
2. Export from `src/public-api.ts` under the matching section (order: core → chrome → forms → overlay → feedback → data → layout).
3. Prefer suite classes (`.suite-*` / `.fj-*`) over local styles.
4. Document selector + props in [`COMPONENTS.md`](../../COMPONENTS.md); add CSS row in `SUITE_COMPONENTS.md` when chrome is new.
5. JSDoc non-obvious inputs/outputs (security, ADR-bound fetch/selection) so Storybook autodocs stay useful.
