# Suite docs — Pass 5

**Styles:** [`suite-docs.css`](./suite-docs.css)
**Hosts:** [ui.deml.app](https://ui.deml.app) · [ui.forjd.co](https://ui.forjd.co)

## Goal

Both Storybooks demonstrate the **same** suite components with the **same** chrome:

- Taxonomy: `Foundation/*` + `Primitives/*` (shared), `Product/*` (DEML-only extensions)
- Story frame: `.suite-story-shell` / `.viking-story-shell` / `.fj-story-shell`
- Tokens: explicit `suite-tokens` → `suite-components` (+ surface CSS as needed)

## Load order (Storybook only)

```
suite-tokens.css → suite-components.css → suite-docs.css → (optional surface CSS)
```

Do **not** load `suite-docs.css` into product apps.

## Manager branding

Both managers use dark suite theme: brand title, void sidebar, electric accent.
