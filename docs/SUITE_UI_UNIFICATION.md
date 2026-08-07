# Suite UI — FORJD (API-only)

**Status:** No public product frontend. HTML shells only.
**Visual SoT:** [deml-ui](https://github.com/dataengineeringformachinelearning/deml-ui) (warm ash NFTS).

## Public hosts

| Host | Surface |
| ---- | ------- |
| [backend.forjd.co](https://backend.forjd.co) | Community-style splash only (FORJD mark + links to community docs) |
| Community docs | [dataengineeringformachinelearning.com/documentation](https://dataengineeringformachinelearning.com/documentation) |
| Community | [dataengineeringformachinelearning.com](https://dataengineeringformachinelearning.com/) |

## Backend chrome

| Layer | Path | Rule |
| ----- | ---- | ---- |
| deml-ui CSS | `backend/static/deml-ui.css` | Vendored via `npm run sync:deml-ui` |
| Shell chrome | `backend/static/forjd-backend.css` | Splash + docs topbar on deml-ui tokens |
| HTML | `backend/app/core/landing_page.py` | Splash only — deml-ui → forjd-backend |

## Hard rules

1. **No forjd-ui / Viking suite** on FORJD — deml-ui only.
2. **No Material / Bootstrap** runtime CSS.
3. **Warm ash** (`#35312D` / `#F3F0EA` / `#2F5F8F`) — not void/electric `#2176ff`.
4. Refresh CSS: `npm run sync:deml-ui` (sibling `deml-ui` dist or deml’s `node_modules/deml-ui`).

## Related

- Community marketing + DEML product own public chrome (deml-ui).
- Historical: former landing-layer ADR removed with the product SPA.
