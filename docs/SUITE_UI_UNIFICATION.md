# Suite UI Unification Mandate (FORJD)

**Status:** Law — FORJD chrome must match DEML / Viking-UI across the suite.  
**Canonical visual SoT:** DEML `packages/viking-ui` (`@dataengineeringformachinelearning/viking-ui`)  
**Full contract:** keep in lockstep with DEML [`docs/SUITE_UI_UNIFICATION.md`](https://github.com/dataengineeringformachinelearning/dataengineeringformachinelearning/blob/main/docs/SUITE_UI_UNIFICATION.md)

## FORJD hosts in scope

| Host | Surface |
| ---- | ------- |
| [forjd.co](https://forjd.co) | Angular landing (`frontend/`) |
| [backend.forjd.co](https://backend.forjd.co) | Splash + Swagger `/docs` + ReDoc `/redoc` |
| [ui.forjd.co](https://ui.forjd.co) | forjd-ui Storybook |

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

## Pass 1 — tokens (done)

Vendored `suite-tokens.css` → forjd-ui + `backend/static/`.  
Refresh: `cd frontend && npm run sync:suite`.

## Pass 2 — component libraries (done)

Vendored `suite-components.css` + Angular primitives with mirrored APIs.

Load order: **suite-tokens → suite-components → suite-landing → app**.

## Pass 3 — product frontend lockstep (done)

- Vendored `suite-landing.css` (void stage + hero / bands / meta)
- `src/app/landing/` is composition-only (no `landing.scss`)
- Logo mark uses suite electric `#2176FF` (cyan retired)

## Pass 4 — backend surfaces (done)

- Vendored `suite-backend.css` — centered logo splash + docs topbar
- `backend/app/core/landing_page.py` — no inline splash CSS
- `/docs` + `/redoc` use `suite-backend-topbar` + `--suite-*` Swagger overrides

## Pass 5 — Storybook lockstep (done)

- Vendored `suite-docs.css` — premium story shells
- Manager branding: `FORJD UI · Suite` (matches Viking-UI suite theme)
- Taxonomy: `Foundation/*` + `Primitives/*` (+ `Product/*` for FORJD-only)
- Preview: fullscreen + suite void backgrounds + Chromatic viewports
- CSS loaded from `.storybook/preview.ts` (suite-tokens / components / docs); decorators from `@storybook/angular-vite`
- Gate: `cd frontend && npm run build-storybook`

## Pass 6 — purity (done)

- Deleted leftover `_typography.scss` + `status-list.scss` (chrome lives in suite CSS)
- `npm run sync:suite` also vendors self-hosted Inter → `public/fonts/inter`
- forjd-ui has zero style npm packages (Angular peers only)
- Local `ng build` critical CSS uses `#2176ff` (deploy clears live cyan lag)
- DEML gate: `npm run suite:purity` (fails on cyan / suite drift / leftover theme files)

### Remaining differences (intentional)

- Product logos/names; DEML-only Storybook Product depth; FORJD Panel/StatusList demos
- Live hosts may lag until deploy

## Phases

1. **Token lock** — done  
2. **Owned chrome CSS** — done  
3. **forjd-ui full primitive set** — done  
4. **Landing lockstep** — done  
5. **Backend lockstep** — done  
6. **Storybook lockstep** — done (`suite-docs.css`)  
7. **Purity** — done (`suite:purity` + Inter sync)
