# forjd-ui component APIs

Angular suite adapter for FORJD. Import **only** from `forjd-ui` (never deep `lib/` paths).

| Doc                                                           | Role                                      |
| ------------------------------------------------------------- | ----------------------------------------- |
| **This file**                                                 | Selectors, props, outputs, usage patterns |
| [`SUITE_COMPONENTS.md`](./src/lib/styles/SUITE_COMPONENTS.md) | CSS class contracts + Viking twins        |
| [`src/lib/README.md`](./src/lib/README.md)                    | Feature groups + import boundaries        |
| Storybook                                                     | Visual + autodocs (`npm run storybook`)   |

Conventions: signal `input()` / `model()` / `output()`; OnPush; suite classes (`.suite-*` / `.fj-*` / `.viking-*`). Soft chrome only — never secrets or ciphertext.

---

## Usage patterns

### Field stack (forms)

```html
<forjd-field label="Tenant id" description="UUID from partner bind" [required]="true">
  <forjd-input name="tenant" [(value)]="tenantId" autocomplete="off" />
</forjd-field>
```

Always wrap controls in `forjd-field` so label / description / error wire `aria-describedby`.

### Overlay open state

```html
<forjd-dialog [(open)]="confirmOpen" title="Erase tenant data?">
  <p>This cannot be undone.</p>
  <forjd-button variant="danger" (click)="erase()">Erase</forjd-button>
</forjd-dialog>

<forjd-sheet [(open)]="prefsOpen" title="Preferences" side="right">
  <forjd-preferences-panel />
</forjd-sheet>
```

`open` is a two-way `model` — prefer `[(open)]`. Native `<dialog>` + focus restore via `NativeDialogSession`.

### Search palette (landing)

```html
<forjd-search-palette
  [(open)]="searchOpen"
  [items]="searchItems"
  placeholder="Search docs, API, and product…"
  (select)="onSearchSelect($event)"
/>
```

```ts
import type { FjSearchPaletteItem } from 'forjd-ui';

const items: FjSearchPaletteItem[] = [
  {
    title: 'Swagger',
    href: 'https://backend.forjd.co/docs',
    group: 'API',
    keywords: ['openapi'],
  },
];
```

⌘K / `/` open when `globalShortcut` is true (default). Closed dialogs must stay `display:none` (suite CSS).

### Preferences + activity (ADR-0024 / 0026 / 0027)

```html
<!-- App shell once -->
<forjd-preferences />
<forjd-toast-host />

<!-- Toolbar -->
<forjd-button type="button" variant="ghost" (click)="prefs.show()"> Preferences </forjd-button>
```

```ts
import { FjPreferencesService } from 'forjd-ui';
// inject(FjPreferencesService).show() — ⌘, also opens
```

Panel hosts theme, export/import (soft chrome pack), and `forjd-activity-list`. Never put tokens in the pack.

### Onboarding checklist (ADR-0025)

```html
<forjd-onboarding-checklist
  flowId="forjd-partner"
  heading="Track your deploy sequence"
  description="Bind → Seal → Project → Operate"
  [steps]="steps"
  (completed)="onGuideDone()"
/>
```

```ts
import type { FjOnboardingStep } from 'forjd-ui';

const steps: FjOnboardingStep[] = [
  { id: 'bind', title: 'Bind', description: 'Mint fjsvc_ for the tenant' },
  { id: 'seal', title: 'Seal', description: 'Client seals envelopes' },
];
```

### Table with selection + fetch states (ADR-0021)

```html
<forjd-table
  [columns]="columns"
  [rows]="rows"
  [selectable]="true"
  [(selectedIds)]="selected"
  [bulkActions]="actions"
  [loading]="handle.loading()"
  [error]="handle.errorMessage()"
  (bulkAction)="onBulk($event)"
/>
```

`bulkAction` payload: `{ action: string; selectedIds: readonly string[] }`.

Bind `loading` / `error` from app `createFetchHandle` — forjd-ui stays presentation-only.

### Progressive disclosure (ADR-0022)

```html
<forjd-disclosure sectionId="advanced-cors" heading="Advanced CORS">
  <!-- collapsed by default; persist via suite-disclosure-v1 -->
</forjd-disclosure>
```

### Toasts

```ts
inject(FjToastService).success('Exported local preferences');
inject(FjToastService).critical('Chunk failed to load', { sticky: true });
```

Mount `<forjd-toast-host />` once near the app root.

### Safe links (ADR-0013)

`forjd-button` / `forjd-nav` run `href` through `safeHref` — `javascript:`, `data:`, and protocol-relative URLs are dropped. `_blank` always gets `rel="noopener noreferrer"`.

---

## Forms

### `forjd-button` · `FjButton`

| Prop         | Type                              | Default     | Notes                                                    |
| ------------ | --------------------------------- | ----------- | -------------------------------------------------------- |
| `variant`    | `FjButtonVariant`                 | `'primary'` | `primary` · `secondary` · `outline` · `danger` · `ghost` |
| `type`       | `'button' \| 'submit' \| 'reset'` | `'button'`  | Ignored when `href` set                                  |
| `href`       | `string?`                         | —           | Rendered as `<a>` when safe                              |
| `target`     | `'_self' \| '_blank'`             | `'_self'`   |                                                          |
| `disabled`   | `boolean`                         | `false`     |                                                          |
| `fullWidth`  | `boolean`                         | `false`     | Host class `.fj-full`                                    |
| `square`     | `boolean`                         | `false`     | Icon-only; pair with `aria-label`                        |
| `aria-label` | `string \| null`                  | `null`      | Required for square / icon-only                          |

Storybook: `Primitives/Button`.

### `forjd-field` · `FjField`

| Prop          | Type      | Default |
| ------------- | --------- | ------- |
| `label`       | `string`  | `''`    |
| `description` | `string?` | —       |
| `error`       | `string?` | —       |
| `required`    | `boolean` | `false` |

Project one control into the default slot. Storybook: `Primitives/Field`.

### `forjd-input` · `FjInput` (CVA)

| Prop           | Type                                                   | Default  |
| -------------- | ------------------------------------------------------ | -------- |
| `type`         | `'text' \| 'email' \| 'password' \| 'url' \| 'search'` | `'text'` |
| `name`         | `string`                                               | `''`     |
| `placeholder`  | `string`                                               | `''`     |
| `autocomplete` | `string`                                               | `''`     |
| `disabled`     | `model<boolean>`                                       | `false`  |
| `value`        | `model<string>`                                        | `''`     |

### `forjd-textarea` · `FjTextarea` (CVA)

| Prop          | Type             | Default |
| ------------- | ---------------- | ------- |
| `name`        | `string`         | `''`    |
| `placeholder` | `string`         | `''`    |
| `rows`        | `number`         | `4`     |
| `disabled`    | `model<boolean>` | `false` |
| `value`       | `model<string>`  | `''`    |

### `forjd-select` · `FjSelect` (CVA)

| Prop          | Type                        | Default |
| ------------- | --------------------------- | ------- |
| `name`        | `string`                    | `''`    |
| `label`       | `string`                    | `''`    |
| `placeholder` | `string`                    | `''`    |
| `options`     | `readonly FjSelectOption[]` | `[]`    |
| `disabled`    | `model<boolean>`            | `false` |
| `value`       | `model<string>`             | `''`    |

`FjSelectOption`: `{ value: string; label: string }`.

### `forjd-checkbox` · `FjCheckbox` (CVA)

| Prop          | Type             | Default |
| ------------- | ---------------- | ------- |
| `description` | `string`         | `''`    |
| `disabled`    | `model<boolean>` | `false` |
| `checked`     | `model<boolean>` | `false` |

Label via projected content.

### `forjd-switch` · `FjSwitch` (CVA)

| Prop       | Type             | Default |
| ---------- | ---------------- | ------- |
| `label`    | `string`         | `''`    |
| `disabled` | `model<boolean>` | `false` |
| `checked`  | `model<boolean>` | `false` |

Storybook (forms stack): `Primitives/Forms`.

---

## Overlay

### `forjd-dialog` · `FjDialog`

| Prop          | Type             | Default |
| ------------- | ---------------- | ------- |
| `open`        | `model<boolean>` | `false` |
| `title`       | `string`         | `''`    |
| `dismissible` | `boolean`        | `true`  |

Slots: default body; use footer actions as projected content.

### `forjd-sheet` · `FjSheet`

| Prop          | Type                | Default   |
| ------------- | ------------------- | --------- |
| `open`        | `model<boolean>`    | `false`   |
| `title`       | `string`            | `''`      |
| `side`        | `'left' \| 'right'` | `'right'` |
| `dismissible` | `boolean`           | `true`    |

### `forjd-search-palette` · `FjSearchPalette`

| Prop               | Type                             | Default       | Notes            |
| ------------------ | -------------------------------- | ------------- | ---------------- |
| `open`             | `model<boolean>`                 | `false`       |                  |
| `items`            | `readonly FjSearchPaletteItem[]` | `[]`          | Curated catalog  |
| `placeholder`      | `string`                         | docs/API copy |                  |
| `globalShortcut`   | `boolean`                        | `true`        | ⌘K / `/`         |
| `recentStorageKey` | `string`                         | suite default | Soft chrome only |

| Output        | Payload               |
| ------------- | --------------------- |
| `queryChange` | `string`              |
| `select`      | `FjSearchPaletteItem` |

### `forjd-preferences` · `FjPreferences`

Host sheet — no inputs. Open via `FjPreferencesService.show()` or ⌘,.

### `forjd-preferences-panel` · `FjPreferencesPanel`

Embeddable panel (theme, data pack, activity). No public inputs; uses injected services.

### `forjd-shortcut-help` · `FjShortcutHelp`

Opened by `FjShortcutHelpService` / `?`. Catalog from `createShortcutRegistry`.

### Toast · `FjToastHost` + `FjToastService`

Mount host once. Service methods: `show`, `success`, `critical`, dismiss helpers. Priority stack max 3 (ADR-0020).

Storybook: `Primitives/Overlay`.

---

## Feedback

### `forjd-badge` · `FjBadge`

| Prop   | Type                  | Default     |
| ------ | --------------------- | ----------- |
| `tone` | `FjTone \| 'neutral'` | `'neutral'` |

`FjTone`: `accent` · `success` · `warning` · `danger` · `gold` (see `tones.ts`).

### `forjd-callout` · `FjCallout`

| Prop      | Type      | Default    |
| --------- | --------- | ---------- |
| `tone`    | `FjTone`  | `'accent'` |
| `heading` | `string?` | —          |

### `forjd-empty` · `FjEmpty`

| Prop          | Type                     | Default         |
| ------------- | ------------------------ | --------------- |
| `title`       | `string`                 | `'No data yet'` |
| `description` | `string`                 | …               |
| `hint`        | `string`                 | `''`            |
| `eyebrow`     | `string`                 | `''`            |
| `showIcon`    | `boolean`                | `true`          |
| `density`     | `'default' \| 'compact'` | `'default'`     |
| `variant`     | `'default' \| 'inset'`   | `'default'`     |

Use `SUITE_EMPTY_GUIDANCE_EYEBROW` for first-time empty guidance.

### `forjd-error-state` · `FjErrorState`

| Prop          | Type     | Default                  |
| ------------- | -------- | ------------------------ |
| `title`       | `string` | `'Something went wrong'` |
| `description` | `string` | recovery copy            |
| `hint`        | `string` | `''`                     |

Project recovery actions into the default slot.

### `forjd-loading` / `forjd-loading-overlay`

| Prop      | Type      | Default      | Component    |
| --------- | --------- | ------------ | ------------ |
| `label`   | `string`  | `'Loading'`  | both         |
| `message` | `string`  | `'Working…'` | both         |
| `detail`  | `string`  | `''`         | both         |
| `full`    | `boolean` | `false`      | overlay only |

### `forjd-skeleton` · `FjSkeleton`

| Prop      | Type                           | Default  |
| --------- | ------------------------------ | -------- |
| `variant` | `'text' \| 'rect' \| 'circle'` | `'text'` |
| `width`   | `string`                       | `'100%'` |
| `height`  | `string`                       | `''`     |

Also: `FjPageSkeleton` + `FjPageSkeletonLayout` for page placeholders.

### `forjd-disclosure` · `FjDisclosure`

| Prop          | Type                   | Default      | Notes       |
| ------------- | ---------------------- | ------------ | ----------- |
| `sectionId`   | `string`               | **required** | Persist key |
| `heading`     | `string`               | **required** |             |
| `description` | `string`               | `''`         |             |
| `defaultOpen` | `boolean`              | `false`      |             |
| `badge`       | `string`               | `'Advanced'` |             |
| `level`       | `'default' \| 'inset'` | `'default'`  |             |

### `forjd-onboarding-checklist` · `FjOnboardingChecklist`

| Prop           | Type                          | Default                        |
| -------------- | ----------------------------- | ------------------------------ |
| `flowId`       | `SuiteOnboardingFlow`         | `null`                         |
| `heading`      | `string`                      | `'Getting started'`            |
| `description`  | `string`                      | `''`                           |
| `eyebrow`      | `string`                      | `SUITE_EMPTY_GUIDANCE_EYEBROW` |
| `steps`        | `readonly FjOnboardingStep[]` | **required**                   |
| `dismissible`  | `boolean`                     | `true`                         |
| `dismissLabel` | `string`                      | `'Dismiss'`                    |
| `finishLabel`  | `string`                      | `"I'm done"`                   |
| `autoHide`     | `boolean`                     | `true`                         |

| Output       | Payload            |
| ------------ | ------------------ |
| `stepChange` | `{ id; complete }` |
| `dismissed`  | `void`             |
| `completed`  | `void`             |

`FjOnboardingStep`: `{ id; title; description?; optional? }`.

---

## Data

### `forjd-table` · `FjTable`

| Prop                              | Type                       | Default   | Notes                       |
| --------------------------------- | -------------------------- | --------- | --------------------------- |
| `columns`                         | `readonly FjTableColumn[]` | `[]`      |                             |
| `rows`                            | `readonly FjTableRow[]`    | `[]`      | stable `id` when selectable |
| `selectable`                      | `boolean`                  | `false`   | ADR-0021                    |
| `selectedIds`                     | `model<readonly string[]>` | `[]`      |                             |
| `bulkActions`                     | `readonly FjBulkAction[]`  | `[]`      |                             |
| `loading`                         | `boolean`                  | `false`   |                             |
| `error`                           | `string`                   | `''`      |                             |
| `errorTitle` / `errorHint`        | `string`                   | defaults  |                             |
| `emptyTitle` / `emptyDescription` | `string`                   | defaults  |                             |
| `virtualThreshold`                | `number`                   | internal  |                             |
| `rowHeight`                       | `number`                   | `44`      |                             |
| `maxHeight`                       | `string`                   | `'28rem'` |                             |
| `overscan`                        | `number`                   | `6`       |                             |

| Output       | Payload                   |
| ------------ | ------------------------- |
| `bulkAction` | `{ action; selectedIds }` |

### `forjd-bulk-toolbar` · `FjBulkToolbar`

| Prop        | Type                      | Default          |
| ----------- | ------------------------- | ---------------- |
| `count`     | `number`                  | `0`              |
| `actions`   | `readonly FjBulkAction[]` | `[]`             |
| `ariaLabel` | `string`                  | `'Bulk actions'` |

| Output        | Payload              |
| ------------- | -------------------- |
| `actionClick` | `string` (action id) |
| `clear`       | `void`               |

### `forjd-tabs` · `FjTabs`

| Prop        | Type                   | Default  |
| ----------- | ---------------------- | -------- |
| `tabs`      | `readonly FjTabItem[]` | `[]`     |
| `value`     | `model<string>`        | `''`     |
| `ariaLabel` | `string`               | `'Tabs'` |

### `forjd-virtual-list` · `FjVirtualList<T>`

| Prop                                 | Type                                          | Default             |
| ------------------------------------ | --------------------------------------------- | ------------------- |
| `items`                              | `readonly T[]`                                | `[]`                |
| `itemHeight`                         | `number`                                      | `96`                |
| `height`                             | `string`                                      | `'24rem'`           |
| `overscan`                           | `number`                                      | `4`                 |
| `label`                              | `string`                                      | `'Scrollable list'` |
| `error` / `errorTitle` / `errorHint` | `string`                                      | defaults            |
| `trackBy`                            | `((item, index) => string \| number) \| null` | `null`              |

Project row template via `ng-template` context (`FjVirtualListItemContext`).

### `forjd-status-list` · `FjStatusList`

| Prop    | Type                      | Default      |
| ------- | ------------------------- | ------------ |
| `items` | `readonly FjStatusItem[]` | **required** |

`FjStatusItem`: `{ name; ok; stateLabel? }`.

### `forjd-stream-status` · `FjStreamStatus`

Calm near-real-time chip — never claims “Live”. Pulse only when connected.

| Prop        | Type                  | Default        |
| ----------- | --------------------- | -------------- |
| `phase`     | `FjStreamStatusPhase` | `'connecting'` |
| `label`     | `string`              | `'Connecting'` |
| `tone`      | `FjStreamStatusTone`  | `'muted'`      |
| `pulse`     | `boolean`             | `false`        |
| `ariaLabel` | `string`              | `''`           |

`FjStreamStatusPhase`: `idle` · `connecting` · `updating` · `paused` · `delayed` · `offline`.

### `forjd-pipeline-flow` · `FjPipelineFlow`

Read-only visual sequence for sealed-stream workflow steps (YAML remains SoT).

| Prop           | Type                         | Default                           |
| -------------- | ---------------------------- | --------------------------------- |
| `steps`        | `readonly FjPipelineStep[]`  | `[]`                              |
| `orientation`  | `'vertical' \| 'horizontal'` | `'horizontal'`                    |
| `label`        | `string`                     | `'Pipeline steps'`                |
| `emptyMessage` | `string`                     | `'No pipeline steps configured.'` |

`FjPipelineStep`: `{ id; title; detail?; kind? }` where `kind` is `process` · `detect` · `unknown`.

### `forjd-activity-list` · `FjActivityList`

| Prop         | Type                            | Default                     |
| ------------ | ------------------------------- | --------------------------- |
| `entries`    | `readonly SuiteActivityEntry[]` | **required**                |
| `emptyLabel` | `string`                        | `'No recent activity yet.'` |

---

## Layout + chrome

### `forjd-page-shell` · `FjPageShell`

| Prop      | Type              | Default     |
| --------- | ----------------- | ----------- |
| `spacing` | `FjLayoutDensity` | `'default'` |

`FjLayoutDensity`: `tight` · `compact` · `default` · `loose`.

### `forjd-section` · `FjSection`

No inputs — semantic section wrapper.

### `forjd-stack` · `FjStack`

| Prop       | Type              | Default     |
| ---------- | ----------------- | ----------- |
| `spacing`  | `FjLayoutDensity` | `'default'` |
| `centered` | `boolean`         | `false`     |

### `forjd-nav` · `FjNav`

| Prop        | Type                   | Default     |
| ----------- | ---------------------- | ----------- |
| `items`     | `readonly FjNavItem[]` | `[]`        |
| `ariaLabel` | `string`               | `'Primary'` |

`FjNavItem`: `{ label; href; current?; external? }` — hrefs sanitized.

### `forjd-card` · `FjCard`

| Prop          | Type      | Default |
| ------------- | --------- | ------- |
| `interactive` | `boolean` | `false` |

### `forjd-panel` · `FjPanel`

| Prop      | Type                  | Default     |
| --------- | --------------------- | ----------- |
| `title`   | `string?`             | —           |
| `variant` | `'section' \| 'card'` | `'section'` |

### `forjd-avatar` · `FjAvatar`

| Prop   | Type                   | Default |
| ------ | ---------------------- | ------- |
| `src`  | `string?`              | —       |
| `alt`  | `string`               | `''`    |
| `name` | `string`               | `''`    | Initials fallback |
| `size` | `'sm' \| 'md' \| 'lg'` | `'md'`  |

### `forjd-separator` · `FjSeparator`

| Prop          | Type                         | Default        |
| ------------- | ---------------------------- | -------------- |
| `orientation` | `'horizontal' \| 'vertical'` | `'horizontal'` |

### `forjd-theme-toggle` · `FjThemeToggle`

No inputs. Cycles system → light → dark via `FjThemeService`.

### Services (inject)

| Service                   | Role                               |
| ------------------------- | ---------------------------------- |
| `FjThemeService`          | Theme preference + persist         |
| `FjPreferencesService`    | Sheet open + theme/activity/export |
| `FjShortcutHelpService`   | `?` help overlay                   |
| `FjCommandHistoryService` | Undo/redo (⌘Z)                     |
| `FjToastService`          | Priority toasts                    |

---

## Core helpers (non-components)

Import from `forjd-ui` when building app infrastructure (not for CSS):

| Helper                                                                                             | Use                                                         |
| -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `safeHref` / `safeHttpBase`                                                                        | Sanitize URLs before paint (ADR-0013)                       |
| `createFetchHandle`                                                                                | **App** `core/fetch` — bind `loading`/`error` to table/list |
| `createPreferencesStore` / `createOnboardingStore` / `createDisclosureStore` / `createActivityLog` | Soft-chrome stores                                          |
| `exportSuiteDataPack` / `applySuiteDataPack`                                                       | Preferences transfer (ADR-0026)                             |
| `createSelectionModel`                                                                             | Multi-select ids (ADR-0021)                                 |
| `runOptimistic`                                                                                    | Persist-with-rollback (ADR-0008)                            |
| `NativeDialogSession`                                                                              | Shared dialog focus session                                 |
| `computeVirtualWindow` / `indicesForWindow`                                                        | Virtualization math                                         |

---

## Storybook map

| Frame                                        | Coverage                                                        |
| -------------------------------------------- | --------------------------------------------------------------- |
| `Foundation/Tokens` · `Typography`           | Design tokens                                                   |
| `Primitives/Button`                          | Variants, link, disabled, square, gallery                       |
| `Primitives/Field` · `Forms`                 | Stack, field error, disabled, checked                           |
| `Primitives/Badge` · `Callout`               | Per-tone + galleries                                            |
| `Primitives/Feedback`                        | Empty, loading, overlay, skeleton, page-skeleton layouts, error |
| `Primitives/Onboarding` · `ErrorBoundary`    | Checklist + boundary                                            |
| `Primitives/Overlay`                         | Dialog, sheet, toast, search, shortcuts                         |
| `Primitives/Chrome`                          | Theme toggle, preferences sheet/panel                           |
| `Primitives/Data`                            | Table (rows/select/loading/error/empty), virtual list, activity |
| `Primitives/Surface` · `Panel` · `PageShell` | Card/nav/tabs/disclosure/avatar compositions                    |
| `Product/StatusList`                         | Mixed / all-ok / all-down / empty                               |

```bash
cd frontend && npm run storybook   # :6006
```

When adding a component: export from `public-api.ts`, document a row here, add/extend a story (major states), keep CSS contracts in `SUITE_COMPONENTS.md`.
