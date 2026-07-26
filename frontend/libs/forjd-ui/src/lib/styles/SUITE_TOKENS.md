# Suite tokens — Pass 1 usage

**Canonical file:** [`suite-tokens.css`](./suite-tokens.css)
**Lock (Role A):** [`suite-tokens.lock.json`](./suite-tokens.lock.json)
**Built:** `packages/viking-ui/dist/suite-tokens.css`
**Vendored FORJD:** `forjd/frontend/libs/forjd-ui/src/lib/styles/suite-tokens.css` (copy — **no npm install for styles**)

Everything downstream must consume **only** these variables. No hard-coded product colors, spacing, radii, or motion outside this system (brand SVG/favicon artwork may use brand navy/blue).

---

## Strategy (intentional)

| Choice        | Decision                                                                                                 |
| ------------- | -------------------------------------------------------------------------------------------------------- |
| Default       | **Dark-first** void austerity (`#0a0a0a`)                                                                |
| Light         | **Opt-in only:** `<html data-theme="light">` — same roles, lightness shift                               |
| Primary       | Electric command — fill `#1565f0` (AA white-on-fill); brand hue `#2176ff` on charts (`--suite-series-1`) |
| Gold          | Institutional `#d4af37` (FORJD) — chrome / prestige; text via `--suite-gold-text`                        |
| Brand artwork | `--suite-brand-navy` / `--suite-brand-blue` — logos only                                                 |
| Type          | Self-hosted **Inter** + system mono stack                                                                |

Inspirations (SpaceX / Palantir / OpenAI / Lockheed / Sequoia) guide density and restraint — **not** new hues.

---

## Where it lives

```text
DEML packages/viking-ui/src/tokens/suite-tokens.css   ← edit here only
        │
        ├─ build-css.mjs → dist/suite-tokens.css (+ prepended into viking-ui / viking-app)
        ├─ python scripts/sync_design_system.py → frontend / marketing / backend static
        └─ forjd: cd frontend && npm run sync:suite  → forjd-ui + backend/static
```

| Prefix       | Role                                 |
| ------------ | ------------------------------------ |
| `--suite-*`  | **Canonical** — use in all new code  |
| `--viking-*` | Alias → suite (viking-ui / deml.app) |
| `--fj-*`     | Alias → suite (forjd-ui / forjd.co)  |

All three resolve to the same computed values via `var()`.

---

## Role cheat sheet (Role A)

| Need                       | Token                                                                                                                                                                                                                                         |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Page background            | `--suite-bg`                                                                                                                                                                                                                                  |
| Subtle page / inset        | `--suite-bg-subtle` / `--suite-surface-inset`                                                                                                                                                                                                 |
| Card / panel               | `--suite-surface`                                                                                                                                                                                                                             |
| Nested well                | `--suite-surface-2`                                                                                                                                                                                                                           |
| Raised control             | `--suite-surface-elevated`                                                                                                                                                                                                                    |
| Body text                  | `--suite-ink`                                                                                                                                                                                                                                 |
| Secondary text             | `--suite-ink-muted`                                                                                                                                                                                                                           |
| Border                     | `--suite-border` / `--suite-border-strong`                                                                                                                                                                                                    |
| CTA / link                 | `--suite-primary` (+ hover / active / soft)                                                                                                                                                                                                   |
| Institutional accent       | `--suite-gold`                                                                                                                                                                                                                                |
| Danger / success / warning | Fills: `--suite-danger` / `--suite-success` / `--suite-warning`. **Foreground on soft surfaces:** `--suite-*-text` (AA)                                                                                                                       |
| Focus ring                 | `--suite-ring` + `--suite-ring-width`                                                                                                                                                                                                         |
| Sans / mono                | `--suite-font-sans` / `--suite-font-mono`                                                                                                                                                                                                     |
| Type scale                 | `--suite-text-2xs` … `--suite-text-display`, plus `--suite-text-headline` / `-quiet` / `-title*` / `-lead*`                                                                                                                                   |
| Spacing                    | `--suite-space-0-5` … `--suite-space-12` (8px grid; THEME numbered scale)                                                                                                                                                                     |
| Touch / control            | `--suite-touch` · `--suite-control-height*` · `--suite-control-px` / `-fs` / `-check` / `-focus-ring`                                                                                                                                         |
| Radius                     | `--suite-radius*` · control `--suite-radius-control` · surface `--suite-radius-surface`                                                                                                                                                       |
| Elevation                  | Recipes `--suite-elevation-1`…`4` / `-hover` / `-inset`; primitives `--suite-shadow-*` + `--suite-highlight`                                                                                                                                  |
| Glass (overlays only)      | `--suite-glass` / `--suite-glass-strong` + `--suite-glass-blur` — never on resting cards                                                                                                                                                      |
| Motion                     | `--suite-duration*` · `--suite-ease*` · `--suite-transition*` · `--suite-hover-lift` / `--suite-press-sink` / `--suite-active-scale` — under `prefers-reduced-motion: reduce`, durations → `0ms`, transitions → `none`, lifts/scale → `0`/`1` |
| Rhythm                     | `--suite-section-gap` (stages) · `--suite-block-gap` (related) · `--suite-density-gap` / `--suite-cluster-gap` (tight)                                                                                                                        |
| Stacking                   | `--suite-z-dropdown` … `--suite-z-toast`                                                                                                                                                                                                      |
| Content width              | `--suite-content-max` (1260px) · `--suite-readable-max` (48rem) · `--suite-page-gutter`                                                                                                                                                       |
| Breakpoints                | `--suite-bp-sm/md/sidebar/lg/xl/2xl` → `600 / 768 / 901 / 1024 / 1440 / 1920`                                                                                                                                                                 |

### Role B — charts

Use `--suite-series-1` … `--suite-series-8` (or `--viking-series-*`). Do not invent chart hexes in product CSS.

### Role C — PDF reports

Print/PDF only (not product UI CSS). Lives in FORJD `fjord-report-tokens.json`.
**Promoted for suite chrome parity (2026-07-26):** report chrome uses suite
primary `#2176ff` and institutional gold `#d4af37`; brand artwork blue `#0078ff`
remains logos/mark-only. Product UI still consumes `suite-tokens.css` only.

---

## Usage

```css
.panel {
  background: var(--suite-surface);
  border: 1px solid var(--suite-border);
  border-radius: var(--suite-radius-surface);
  padding: var(--suite-space-3);
  color: var(--suite-ink);
  /* Resting: hairline only; use elevation-3+ for floating chrome */
  box-shadow: var(--suite-elevation-1);
  transition: var(--suite-transition);
}

.panel[data-elevated="true"] {
  border-color: var(--suite-border-strong);
  box-shadow: var(--suite-elevation-3);
}

.cta {
  background: var(--suite-primary);
  color: var(--suite-ink-on-primary);
  min-height: var(--suite-touch);
  border-radius: var(--suite-radius-control);
  font: var(--suite-weight-semibold) var(--suite-text-md) /
    var(--suite-leading-snug) var(--suite-font-sans);
}

.cta:focus-visible {
  outline: var(--suite-ring-width) solid var(--suite-ring);
  outline-offset: var(--suite-ring-offset);
}

/* Aliases — identical computed values */
.legacy {
  color: var(--viking-text); /* = --suite-ink */
  color: var(--fj-text); /* = --suite-ink */
}
```

```html
<link rel="stylesheet" href="/path/to/suite-tokens.css" />
<!-- then suite-components / suite-landing / app styles that only use var(--suite-*) -->
```

**Load order:** `suite-fonts` → **`suite-tokens`** → `suite-components` → surface CSS → app.

---

## Theme preference (light / dark / system)

| Piece     | Contract                                                                |
| --------- | ----------------------------------------------------------------------- |
| Attribute | `<html data-theme="light\|dark">` — resolved appearance only            |
| Storage   | `suite-theme` = `light` \| `dark` \| `system` (legacy `theme` migrated) |
| Default   | `system` → `prefers-color-scheme`                                       |
| Apply     | `VikingThemeService` / `FjThemeService` + FOUC `<head>` script          |
| Control   | `viking-theme-toggle` / `forjd-theme-toggle` / `.suite-theme-toggle`    |

```html
<!-- FOUC: read suite-theme → resolve system → set data-theme before paint -->
<html data-theme="dark">
  …
  <viking-theme-toggle
    [theme]="theme()"
    [preference]="preference()"
    (toggle)="toggle()"
  />
</html>
```

When preference is `system`, OS changes update `data-theme` live. Toggle persists an explicit light/dark choice; `cyclePreference()` / `useSystemPreference()` restore system.

---

## Rules

1. **Edit DEML `suite-tokens.css` only** for visual tokens. Same PR: update `suite-tokens.lock.json` if Role A hexes change.
2. **No hard-coded colors** outside this file (exception: brand SVG assets using brand navy/blue).
3. **No magic spacing/radius/duration** — use `--suite-space-*` / `--suite-radius-*` / `--suite-duration*`.
4. **Prefer `--suite-*`** in new CSS; `--viking-*` / `--fj-*` are compatibility aliases only.
5. **Do not invent new `--fj-space-*`** — frozen legacy map; use `--suite-space-*`.
6. **Sync FORJD** after token edits: `cd forjd/frontend && npm run sync:suite`.
7. **Gate:** `npm run suite:purity` (includes Role A lock check).

---

## Verify

```bash
# DEML
node packages/viking-ui/scripts/check-suite-tokens.mjs
npm run suite:purity

# FORJD (sibling checkout)
cd frontend && npm run sync:suite
# suite-tokens.css SHA must match DEML
```

---

## Deprecated

| Value                                               | Replacement                 |
| --------------------------------------------------- | --------------------------- |
| `#00b4ff` (FORJD cyan product primary)              | `--suite-primary` `#2176ff` |
| Hard-coded navy stepped product surfaces as page bg | `--suite-bg` void `#0a0a0a` |
| `#c4a035` as institutional gold                     | `--suite-gold` `#d4af37`    |
