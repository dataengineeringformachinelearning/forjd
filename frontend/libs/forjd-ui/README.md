# forjd-ui

Custom Angular UI primitives for FORJD. Built from scratch — no Material.

## What's here now

- Dark-first design tokens (`src/lib/styles/_tokens.scss`)
- `FjButton` (`<forjd-button>`) — first primitive

## Local consumption

The app imports via path mapping to source (`tsconfig.json` → `forjd-ui`).
No library rebuild needed while iterating.

```ts
import { FjButton } from 'forjd-ui';
```

## Build the package (later)

```bash
ng build forjd-ui
```
