# Suite UI Unification Mandate (FORJD)

**Status:** Law — FORJD chrome must match DEML / Viking-UI across the suite.
**Canonical visual SoT:** DEML `packages/viking-ui` (`@dataengineeringformachinelearning/viking-ui`)
**Full contract:** keep in lockstep with DEML [`docs/SUITE_UI_UNIFICATION.md`](https://github.com/dataengineeringformachinelearning/deml/blob/main/docs/SUITE_UI_UNIFICATION.md)
**ADR (landing layers + adapter):** [`adr/0006-landing-layers-suite-adapter.md`](adr/0006-landing-layers-suite-adapter.md)

## FORJD hosts in scope

| Host | Surface |
| ---- | ------- |
| [forjd.co](https://forjd.co) | Angular landing (`frontend/`) |
| [backend.forjd.co](https://backend.forjd.co) | Splash + Swagger `/docs` + ReDoc `/redoc` |
| forjd-ui Storybook (local / Chromatic) | Public `ui.forjd.co` retired |

## Local ownership

| Layer | Path | Rule |
| ----- | ---- | ---- |
| Tokens | `frontend/libs/forjd-ui/src/lib/styles/suite-tokens.css` | Vendored `--suite-*` (+ `--fj-*` / `--viking-*` aliases) |
| Component chrome | `…/suite-components.css` | Owned primitives; dual selectors `.suite-*` / `.viking-*` / `.fj-*` |
| Angular adapters | `frontend/libs/forjd-ui/src/lib/*/` | Headless behavior + suite classes; Storybook stories |
| App composition | `frontend/src/` | No reusable look left in the app |
| API docs theme | `backend/app/core/*_page.py` + `backend/static/` | Load suite-tokens + suite-components |

## Hard rules

1. **Own the look.** No Material / Bootstrap / Blueprint / shadcn runtime CSS. Patterns only.
2. **forjd-ui is an adapter**, not a fork. Do not invent a second palette or radius system.
3. **Deprecated product primary:** `#00b4ff` → use suite electric `#2176ff` (`--fj-primary`).
4. **Void surfaces stay:** `#0a0a0a` / `#111111` / `#1a1a1a`.
5. **Expand components in forjd-ui first**, then consume from the app.

## Pass 1 — tokens (locked 2026-07-25)

Vendored `suite-tokens.css` (+ usage `SUITE_TOKENS.md`) → forjd-ui + `backend/static/`.
Canonical + Role A lock live in DEML `packages/viking-ui/src/tokens/` (`suite-tokens.lock.json`).
Refresh: `cd frontend && npm run sync:suite`.

## Pass 2 — component libraries (locked 2026-07-25)

Vendored `suite-components.css` + Angular primitives with mirrored APIs and **triple classes** (`suite-*` + `fj-*` + `viking-*`).

Load order: **suite-tokens → suite-components → suite-landing → app**.
Canonical chrome + contracts: DEML `packages/viking-ui/src/tokens/suite-components.css` + `SUITE_COMPONENTS.md`.

## Pass 3 — product frontend lockstep (locked 2026-07-25)

- Vendored `suite-landing.css` (void stage + vivid hero / bands / meta)
- `src/app/landing/` is composition-only (no `landing.scss`)
- Live badge + brand → headline → lede → suite CTAs match deml.app / marketing DNA
- Logo mark uses suite electric `#2176FF` (cyan retired)

## Pass 4 — backend surfaces (locked 2026-07-25)

- Vendored `suite-backend.css` — **perfectly centered** logo splash + sticky docs topbar
- `landing_page.py` / `docs_page.py` / `redoc_page.py` load suite-fonts → tokens → components → backend
- Inter faces at `backend/static/fonts/inter/` (sync rewrites suite-fonts paths)
- Quiet Swagger method chips (no multicolored rainbow)
- No inline splash hex (cyan retired)

## Pass 5 — Storybook lockstep (locked 2026-07-25)

- Vendored `suite-docs.css` — premium story shells (no local shell redefinition)
- Manager branding: **`Suite UI · FORJD`** (same palette as `Suite UI · Viking`)
- Taxonomy: `Foundation/*` + `Primitives/*` (+ `Product/*` for FORJD-only demos)
- Preview: fullscreen + suite void backgrounds + Chromatic viewports
- Decorator: `.suite-story-shell` + `.suite-story-panel` (triple-classed with viking/fj)
- CSS: suite-fonts → tokens → components → docs via `preview.ts`
- Gate: `cd frontend && npm run build-storybook`

## Pass 6 — purity (locked 2026-07-25)

- No leftover `_typography.scss` / `status-list.scss` / `landing.scss` (gate fails if reintroduced)
- `npm run sync:suite` vendors suite CSS + Inter (frontend `/fonts` + backend `/static/fonts`)
- forjd-ui: Angular peers + tslib only (no style npm packages)
- Landing loads suite-fonts → tokens → components → backend (no inline cyan)
- DEML `npm run suite:purity` enforces sibling lockstep + Pass 1–5 contracts
- FORJD CI runs `suite:purity` (foundation). Residual host holes → Pass 7.

## Pass 7 — interaction identity (in progress · 2026-07-26)

One visual / spacing / motion / interaction language across adapters:

- **Panel titles** live in `suite-components.css` (triple selectors) — Storybook no longer depends on landing CSS
- **Tabs / disclosure / bulk toolbar** share button-class hover/press/focus/disabled + `--suite-transition*`
- **`--fj-*` aliases** expanded for ring, radius scale, transition, ease-emphasized, primary-active
- Landing meta links use `.suite-link` triple classes; backend splash hover uses `--suite-hover-lift`
- Contract: `SUITE_COMPONENTS.md` → “Interaction / motion / spacing language”
- **G1 closed (FORJD):** self-hosted swagger-ui-dist + redoc under `backend/static/vendor/`; owned `suite-apidocs.css`; CSP drops jsDelivr for HTML shells; durable `forjd-tab-panel` projection
- Remaining (completion design): Chromatic hard-gate, DEML CI purity, soft-migrate retirement — see [`SUITE_UI_UNIFICATION_COMPLETION.md`](SUITE_UI_UNIFICATION_COMPLETION.md)

### Remaining differences (intentional)

- Product logos/names; DEML-only Storybook Product depth; FORJD Panel/StatusList demos
- **Deploy:** live `backend.forjd.co` must be redeployed after suite CSS sync

## Phases

1. **Token lock** — done
2. **Owned chrome CSS** — done
3. **forjd-ui full primitive set** — done
4. **Landing lockstep** — done
5. **Backend lockstep** — done
6. **Storybook lockstep** — done (`suite-docs.css`)
7. **Purity (foundation)** — done (`suite:purity` + Inter sync)
8. **Interaction identity** — in progress (Pass 7)
