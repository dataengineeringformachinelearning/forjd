# forjd-ui

Custom Angular UI primitives for FORJD. Built from scratch — no Material.
**Pass 1–2:** vendored suite tokens + component chrome from DEML Viking-UI.

| Artifact            | Path                                                                                                                 |
| ------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Component APIs**  | [`COMPONENTS.md`](./COMPONENTS.md) — props, outputs, usage patterns                                                  |
| Layout / boundaries | [`src/lib/README.md`](./src/lib/README.md)                                                                           |
| Tokens              | [`suite-tokens.css`](./src/lib/styles/suite-tokens.css)                                                              |
| Chrome              | [`suite-components.css`](./src/lib/styles/suite-components.css)                                                      |
| Landing             | [`suite-landing.css`](./src/lib/styles/suite-landing.css)                                                            |
| CSS contracts       | [`SUITE_TOKENS.md`](./src/lib/styles/SUITE_TOKENS.md), [`SUITE_COMPONENTS.md`](./src/lib/styles/SUITE_COMPONENTS.md) |

Load order (app): **suite-tokens → suite-components → suite-landing → app**.
Load order (Storybook): **suite-tokens → suite-components → suite-docs**.

No npm install for styles. Canonical source: DEML `packages/viking-ui/src/tokens/`.

## Primitives (Angular)

Forms: Button, Field, Input, Textarea, Select, Checkbox, Switch
Overlay: Dialog, Sheet, Search palette, Preferences, Shortcut help, Toast
Feedback: Badge, Callout, Empty, Error state, Loading, Skeleton, Disclosure, Onboarding checklist, Error boundary
Data: Table, Bulk toolbar, Tabs, Virtual list, Status list, Activity list
Layout: Page shell / Section / Stack, Nav, Card, Panel, Avatar, Separator
Chrome: Theme toggle + preferences / theme / shortcut / command-history services

Pattern: **headless behavior + suite classes** (`.suite-*` / `.fj-*` / `.viking-*`). Same look as DEML with zero extra styling.

Full prop tables and recipes: **[`COMPONENTS.md`](./COMPONENTS.md)**.

## Local consumption

```ts
import {
  FjButton,
  FjField,
  FjInput,
  FjSearchPalette,
  FjPreferencesService,
  FjToastHost,
  FjToastService,
  type FjSearchPaletteItem,
} from 'forjd-ui';
```

```bash
cd frontend
npm run sync:suite      # vendor CSS from DEML (FORJD_DEML_ROOT override)
npm run suite:purity
npm run storybook       # interactive API + visuals
```

## Storybook + Chromatic

Major components and states live under `Primitives/*` and `Product/*` (see [`COMPONENTS.md`](./COMPONENTS.md) → Storybook map).

```bash
npm run storybook
npm run build-storybook
npm run chromatic
```

Public Storybook hosting (`ui.forjd.co`) is retired — use local `npm run storybook` / Chromatic.
