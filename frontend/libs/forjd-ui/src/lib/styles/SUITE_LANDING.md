# Suite landing — Pass 3

**Styles:** [`suite-landing.css`](./suite-landing.css)
**Depends on:** [`suite-tokens.css`](./suite-tokens.css), [`suite-components.css`](./suite-components.css)

## Goal

forjd.co, deml.app `/`, and dataengineeringformachinelearning.com share one product-family stage:

- Void atmosphere (electric + gold radials + sparse grid mask)
- Tall hero with brand → headline → lede → CTA row
- Section tags, capability bands, metric lists, meta strips

## Class contracts

| Role                        | Classes                                                                      |
| --------------------------- | ---------------------------------------------------------------------------- |
| Stage                       | `.suite-landing` / `.fj-landing` / `.landing-container` / `.community-home`  |
| Hero (copy stack)           | `.suite-landing-hero` / `.landing__hero`                                     |
| Hero (copy + panel)         | `.hero-showcase` (grid from `marketing-landing.scss`)                        |
| Brand                       | `.suite-landing-brand` / `.hero-brand`                                       |
| Actions                     | `.suite-landing-actions` / `.viking-unified-hero-actions`                    |
| Section header              | `.suite-landing-section-header` / `.viking-unified-section-header`           |
| Steps / grid / bands / meta | `.suite-landing-steps`, `-grid`, `-bands`, `-meta` (+ `.landing__*` aliases) |

## Load order

```
suite-tokens.css → suite-components.css → suite-landing.css → app / viking-app / viking-ui
```

FORJD: `npm run sync:suite`
DEML: `npm run build:viking-ui:package` + `python scripts/sync_design_system.py`
