# Frontend

FORJD Angular app + `libs/forjd-ui` component library.

The public product landing at `/` is static forjd-ui composition: brand, product
summary, capability panels, and links to the API Swagger/ReDoc. There is no
runnable console or in-app stack control surface.

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

### Storybook (local / Chromatic only)

Public Storybook hosting (`ui` / `ui.forjd.co`) is **retired**. forjd-ui components stay in `libs/forjd-ui/`.

| Vercel project | Domain   | Build           | Output                  |
| -------------- | -------- | --------------- | ----------------------- |
| `forjd`        | forjd.co | `npm run build` | `dist/frontend/browser` |

```bash
# Local Storybook
cd frontend && npm run storybook
cd frontend && npm run build-storybook && npx serve dist/storybook/forjd-ui

# Product site only
npx vercel deploy --prod --yes --project forjd
```
