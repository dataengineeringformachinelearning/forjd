# forjd-ui

Custom Angular UI primitives for FORJD. Built from scratch — no Material.

## What's here now

- Dark-first FJORD design tokens (`src/lib/styles/_tokens.scss`)
- `FjButton` (`<forjd-button>`) — first primitive + Storybook stories

## Local consumption

The app imports via path mapping to source (`tsconfig.json` → `forjd-ui`).
No library rebuild needed while iterating.

```ts
import { FjButton } from 'forjd-ui';
```

## Storybook + Chromatic

Develop components in isolation, then publish visual baselines.

```bash
# local component workshop (http://localhost:6006)
npm run storybook

# static build (also what Chromatic uploads)
npm run build-storybook

# publish to Chromatic (needs CHROMATIC_PROJECT_TOKEN)
npm run chromatic
```

### First-time Chromatic link

1. Create a project at [chromatic.com](https://www.chromatic.com) (GitHub login).
2. Copy the project token.
3. Either export it once: `export CHROMATIC_PROJECT_TOKEN=…`
   or add it as a GitHub Actions / Vercel secret later.
4. Run `npm run chromatic` from `frontend/`.

Add a new `*.stories.ts` next to each component as you build the library.

## Build the package (later)

```bash
ng build forjd-ui
```
