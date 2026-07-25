# forjd-ui

Custom Angular UI primitives for FORJD. Built from scratch — no Material.
**Pass 1–2:** vendored suite tokens + component chrome from DEML Viking-UI.

| Artifact | Path |
| -------- | ---- |
| Tokens | [`suite-tokens.css`](./src/lib/styles/suite-tokens.css) |
| Chrome | [`suite-components.css`](./src/lib/styles/suite-components.css) |
| Landing | [`suite-landing.css`](./src/lib/styles/suite-landing.css) |
| Contracts | [`SUITE_TOKENS.md`](./src/lib/styles/SUITE_TOKENS.md), [`SUITE_COMPONENTS.md`](./src/lib/styles/SUITE_COMPONENTS.md) |

Load order (app): **suite-tokens → suite-components → suite-landing → app**.  
Load order (Storybook / ui.forjd.co): **suite-tokens → suite-components → suite-docs**.

No npm install for styles. Canonical source: DEML `packages/viking-ui/src/tokens/`.

## Primitives

Button, Input, Textarea, Select, Checkbox, Switch, Card, Badge, Dialog, Sheet, Tabs, Table, Nav, Toast, Skeleton, Empty, Avatar, Separator, Field, Callout, Panel, PageShell / Section / Stack, StatusList.

Pattern: **headless behavior + suite classes** (`.suite-*` / `.fj-*` / `.viking-*`). Same look as DEML with zero extra styling.

## Local consumption

```ts
import {
  FjButton,
  FjCard,
  FjDialog,
  FjField,
  FjInput,
  FjToastHost,
  FjToastService,
} from 'forjd-ui';
```

Load order (angular.json / Storybook): **suite-tokens → suite-components → app styles**.

```bash
npm run sync:suite
```

## Storybook + Chromatic

```bash
npm run storybook
npm run build-storybook
npm run chromatic
```

Public Storybook: [ui.forjd.co](https://ui.forjd.co) — see [`ui/README.md`](../../ui/README.md).
