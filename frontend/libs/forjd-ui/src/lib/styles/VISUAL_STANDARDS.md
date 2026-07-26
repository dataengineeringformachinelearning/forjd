# Visual standards checklist (forjd-ui)

Adapter checklist. Canonical SoT is DEML `packages/viking-ui/VISUAL_STANDARDS.md` + `THEME.md`.

**Grid:** 8px primary (`--suite-space-unit`).  
**Aesthetic:** void-black command + electric `#2176ff` + gold — restrained, high-signal.

## Before merge
- [ ] Consume `--suite-*` / `--fj-*` only — no raw hex/px inventing
- [ ] Suite CSS synced from DEML (`npm run sync:suite`) — do not hand-drift tokens
- [ ] Interactive primitives have hover / active / focus-visible / disabled
- [ ] Fields set `data-invalid`; nav sets `aria-current="page"`
- [ ] Tables use empty + skeleton states (not plain “No rows” text)
- [ ] Tabs support Arrow / Home / End keyboard movement
- [ ] Touch targets ≥ `--suite-touch` (44px) on mobile
- [ ] No glow/pulse noise on landing chrome
- [ ] WCAG AA contrast + `prefers-reduced-motion` respected
