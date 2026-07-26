# Suite landing — Pass 3

**Styles:** [`suite-landing.css`](./suite-landing.css)
**Depends on:** [`suite-tokens.css`](./suite-tokens.css), [`suite-components.css`](./suite-components.css)
**Gate:** `node packages/viking-ui/scripts/check-suite-landing.mjs` (via `suite:purity`)

## Goal

**forjd.co**, **deml.app `/`**, and **dataengineeringformachinelearning.com** share one product-family DNA:

| Layer      | Shared contract                                                                                                                                      |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Atmosphere | Void `#0a0a0a` + one electric wash + quiet grid mask                                                                                                 |
| Hero       | Status badge → brand → headline → lede → ≤2 suite-btn CTAs                                                                                           |
| Sections   | Title/lede + steps / bands (tags optional; avoid stacked ALL-CAPS)                                                                                   |
| Chrome     | Pass 2 suite components only (cards, buttons, links)                                                                                                 |
| Motion     | Instant hero (no stagger); pulse only when `.pulse-dot` + Live; no card lift                                                                         |
| Ready UX   | One story: `data-phase=loading\|ready\|degraded` — Confirming → Production (+ pulse) → Offline/Unavailable/Not ready + Try again                     |
| Devices    | High-end: electric wash + grid. Constrained (`max-width: 600px` / `prefers-reduced-data`): solid void, no hairlines; 44px touch; short-viewport hero |

Calm confidence over clever theater — **fast** (CSS-only atmosphere, no JS animation libs).

## Class contracts

| Role              | Canonical                          | Aliases (lockstep)                                              |
| ----------------- | ---------------------------------- | --------------------------------------------------------------- |
| Stage             | `.suite-landing`                   | `.fj-landing` · `.landing-container` · `.community-home`        |
| Hero              | `.suite-landing-hero`              | `.landing__hero` · `.viking-unified-hero`                       |
| Live badge        | `.suite-landing-badge`             | `.hero-badge` · `.viking-unified-hero-badge`                    |
| Brand             | `.suite-landing-brand`             | `.hero-brand` · `.fj-brand`                                     |
| Headline          | `.suite-landing-headline`          | `.landing__hero-line` · `.title` · `.viking-unified-hero-title` |
| Lede              | `.suite-landing-lede`              | `.subtitle` · `.viking-unified-hero-lead` · `.fj-lede`          |
| Actions           | `.suite-landing-actions`           | `.cta-group` · `.viking-unified-hero-actions`                   |
| Actions primary   | `.suite-landing-actions-primary`   | `.landing__actions-primary` — command CTAs (≤3)                 |
| Actions secondary | `.suite-landing-actions-secondary` | Quiet ghosts / theme; no hover lift                             |
| Section header    | `.suite-landing-section-header`    | `.viking-unified-section-header` · `.quick-start-header`        |
| Tag               | `.suite-landing-tag`               | `.section-tag` · `.landing__tag`                                |
| Steps             | `.suite-landing-steps`             | `.landing__steps` · `.quick-start-steps`                        |
| Grid              | `.suite-landing-grid`              | `.landing__grid` · `.community-showcase-grid`                   |
| Band              | `.suite-landing-band`              | `.landing__band` · `.showcase-band`                             |
| Metrics           | `.suite-landing-metric-list`       | `.landing__metric-list` · `.visual-metrics`                     |
| Meta              | `.suite-landing-meta`              | `.landing__meta`                                                |

## Markup pattern (all three hosts)

```html
<div class="suite-landing fj-landing landing-container">
  <section class="suite-landing-hero">
    <p class="suite-landing-badge"><span class="badge-dot"></span> …</p>
    <p class="suite-landing-brand">FORJD</p>
    <h1 class="suite-landing-headline">…</h1>
    <p class="suite-landing-lede">…</p>
    <div class="suite-landing-actions">
      <a class="suite-btn viking-btn" data-variant="primary">…</a>
    </div>
  </section>
  <!-- sections: suite-landing-section-header + steps | bands | grid -->
</div>
```

## Load order

```
suite-fonts → suite-tokens → suite-components → suite-landing → app
```

| Host      | How it loads                             |
| --------- | ---------------------------------------- |
| forjd.co  | angular.json styles array                |
| deml.app  | `viking-app.css` (suite bundle appended) |
| marketing | `viking-ui.css` (suite bundle appended)  |

**FORJD:** `cd frontend && npm run sync:suite`
**DEML:** `npm run build:viking-ui:package` + `python scripts/sync_design_system.py`

## Rules

1. **No page-level SCSS** for landing chrome on forjd / deml product-home / marketing home.
2. **Atmosphere is suite-only** when `.suite-landing` is present (marketing-landing.scss must not double-glow).
3. **CTAs are suite-btn** variants only.
4. **Cards are suite-card** (or viking-card dual-classed).
5. Prefer canonical `.suite-landing-*` names in new markup; aliases remain for migration.

## Verify

```bash
npm run suite:landing
npm run suite:purity
# Visual: forjd.co · deml.app/ · dataengineeringformachinelearning.com
```
