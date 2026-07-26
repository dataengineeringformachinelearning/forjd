# Frontend

FORJD Angular app + `libs/forjd-ui` component library.

The public product landing at `/` is static forjd-ui composition: brand, product
summary, capability panels, and links to the API Swagger/ReDoc. There is no
runnable console or in-app stack control surface.

**Layers:** presentation (`landing/`) vs domain/infra (`core/`) — see
[`src/app/README.md`](src/app/README.md). forjd-ui stays presentation-only.

**Offline:** production builds register Angular ngsw (app shell + navigation
fallback). The landing distinguishes browser offline from API unreachable
([ADR-0009](../docs/adr/0009-graceful-offline-landing.md)) — not an offline data plane.

## App

```bash
nvm use                 # Node 24 (.nvmrc)
npm run preflight       # engines + suite CSS
npm start               # http://127.0.0.1:4200 (HMR)
npm run start:poll      # if watchers hit EMFILE
npm run clean:cache     # stuck Vite / Angular cache
npm run format:check    # Prettier
npm run typecheck       # tsc --noEmit (app + forjd-ui)
npm run build           # also enforces strictTemplates
npm test
```

From repo root, install git hooks once: `npm run install-hooks`.

Dev builds point at `http://127.0.0.1:8000` via `src/environments/environment.development.ts`.

Local DX (suite sync, doctor, quality): [`../docs/DEV.md`](../docs/DEV.md).

forjd-ui APIs (props / usage): [`libs/forjd-ui/COMPONENTS.md`](./libs/forjd-ui/COMPONENTS.md).

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
