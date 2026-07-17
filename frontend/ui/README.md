# ui.forjd.co — public Storybook

Vercel project **`ui`** serves forjd-ui Storybook. The app project **`forjd`** serves [forjd.co](https://forjd.co).

Both use Root Directory `frontend/`. Build commands are set **per project** in Vercel (not in `vercel.json`):

| Project | Domain | Build | Output |
|---------|--------|-------|--------|
| `forjd` | forjd.co | `npm run build` | `dist/frontend/browser` |
| `ui` | ui.forjd.co | `npm run build-storybook` | `dist/storybook/forjd-ui` |

`frontend/vercel.json` only has shared SPA rewrites + PWA headers.

## Deploy (CLI)

From the **repo root** (so Root Directory `frontend` resolves correctly):

```bash
npx vercel deploy --prod --yes --project ui     # Storybook
npx vercel deploy --prod --yes --project forjd  # app
```

## Local check

```bash
cd frontend
npm run build-storybook
npx serve dist/storybook/forjd-ui
```
