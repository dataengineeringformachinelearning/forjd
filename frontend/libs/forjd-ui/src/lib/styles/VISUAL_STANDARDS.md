# Visual standards checklist (forjd-ui)

Adapter checklist. Canonical SoT is DEML `packages/viking-ui/VISUAL_STANDARDS.md` + `THEME.md`.

**Grid:** 8px primary (`--suite-space-unit`).
**Aesthetic:** void-black command + electric `#2176ff` + gold — restrained, high-signal.

## Before merge

- [ ] Consume `--suite-*` / `--fj-*` only — no raw hex/px inventing
- [ ] Suite CSS synced from DEML (`npm run sync:suite`) — do not hand-drift tokens
- [ ] Preload `/fonts/inter/InterVariable.woff2`; hero mark uses SVG + `fetchpriority="high"`
- [ ] Content images: dimensions + `loading="lazy"` / `decoding="async"`
- [ ] Interactive primitives share one language: hover lift / press sink / `:focus-visible` ring / disabled opacity (`SUITE_COMPONENTS.md` Pass 7)
- [ ] Motion via `--suite-transition*` + `--suite-hover-lift` / `--suite-press-sink` — never raw `translateY(-1px)`
- [ ] Spacing via `--suite-space-*` / control grid (`--suite-touch` → `--suite-control-height`)
- [ ] Panel titles use `.suite-panel-title` (components CSS — not landing-only)
- [ ] Buttons/fields/tabs/nav/disclosure/bulk toolbar use triple classes (`.suite-*` / `.fj-*` / `.viking-*`)
- [ ] Fields set `data-invalid`; nav sets `aria-current="page"`
- [ ] Tables use empty + skeleton states (not plain “No rows” text)
- [ ] Tabs support Arrow / Home / End keyboard movement
- [ ] Touch targets ≥ `--suite-touch` (44px) on mobile
- [ ] Depth via `--suite-elevation-*` / `--fj-elevation-*` only — resting = 1, floating = 3–4
- [ ] Glass (`--suite-glass*`) on overlays only; honor `prefers-reduced-transparency`
- [ ] No glow/pulse noise on landing chrome
- [ ] WCAG 2.2 AA contrast + focus not obscured + `prefers-reduced-motion` respected
- [ ] Storybook story covers idle / hover-relevant / disabled / empty states for new primitives
- [ ] Landing hero: ≤3 primary CTAs; secondary ghosts without hover lift; brand-first type rhythm
- [ ] Landing cards: top hairline + 1px lift hover; metric lists drop last border
- [ ] Callouts use inset tone rail; live badge pulse respects reduced-motion
