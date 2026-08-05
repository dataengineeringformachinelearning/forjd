# Suite UI — FORJD (API-only)

**Status:** Superseded product landing retired. FORJD has **no public product frontend**.
**Visual SoT for HTML shells:** [deml-ui](https://github.com/dataengineeringformachinelearning/deml-ui) (warm ash NFTS).

## Public hosts

| Host | Surface |
| ---- | ------- |
| [backend.forjd.co](https://backend.forjd.co) | Splash + Swagger `/docs` + ReDoc `/redoc` |
| ~~forjd.co~~ | **Retired** — community story lives on [dataengineeringformachinelearning.com](https://dataengineeringformachinelearning.com/) |

## Backend chrome

| Layer | Path | Rule |
| ----- | ---- | ---- |
| deml-ui CSS | `backend/static/deml-ui.css` | Vendored via `npm run sync:deml-ui` |
| Shell chrome | `backend/static/forjd-backend.css` | Splash + docs topbar on deml-ui tokens |
| HTML | `backend/app/core/landing_page.py`, `docs_page.py`, `redoc_page.py` | Load deml-ui → forjd-backend |

## Hard rules

1. **No forjd-ui / Viking suite** on FORJD — deml-ui only.
2. **No Material / Bootstrap** runtime CSS.
3. **Warm ash** (`#35312D` / `#F3F0EA` / `#2F5F8F`) — not void/electric `#2176ff`.
4. Refresh CSS: `npm run sync:deml-ui` (sibling `deml-ui` dist or deml’s `node_modules/deml-ui`).

## Related

- Community marketing: deml-ui on dataengineeringformachinelearning.com
- DEML product: deml.app (deml-ui)
- ADR: [`adr/0006-landing-layers-suite-adapter.md`](adr/0006-landing-layers-suite-adapter.md) (historical; landing removed)
