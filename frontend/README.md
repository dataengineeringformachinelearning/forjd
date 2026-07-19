# Frontend

FORJD Angular app + `libs/forjd-ui` component library.

The public product landing at `/` is static: brand, product summary, and links to
API documentation. There is no runnable console or in-app stack control surface.

## App

```bash
npm start          # http://localhost:4200
npm run build
npm test
```

Dev builds point at `http://127.0.0.1:8000` via `src/environments/environment.development.ts`.

## forjd-ui (Storybook + Chromatic)

Build UI primitives in isolation, then publish visuals to Chromatic.

```bash
npm run storybook          # http://localhost:6006
npm run build-storybook    # dist/storybook/forjd-ui
npm run chromatic          # needs CHROMATIC_PROJECT_TOKEN
```

Put new stories next to components: `libs/forjd-ui/src/lib/<name>/<name>.stories.ts`.

See `libs/forjd-ui/README.md` for Chromatic first-time setup.

### Public Storybook (ui.forjd.co)

| Vercel project | Domain | Build | Output |
|----------------|--------|-------|--------|
| `forjd` | forjd.co | `npm run build` | `dist/frontend/browser` |
| `ui` | ui.forjd.co | `npm run build-storybook` | `dist/storybook/forjd-ui` |

Both use Root Directory `frontend/`. Build commands are set **per project** in Vercel.
`vercel.json` has shared SPA rewrites + PWA headers; Storybook may use `vercel.ui.json`.

```bash
# From repo root
npx vercel deploy --prod --yes --project ui     # Storybook
npx vercel deploy --prod --yes --project forjd  # app

# Local check
cd frontend && npm run build-storybook && npx serve dist/storybook/forjd-ui
```
