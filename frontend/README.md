# Frontend

FORJD Angular app + `libs/forjd-ui` component library.

## App

```bash
npm start          # http://localhost:4200
npm run build
npm test
```

## forjd-ui (Storybook + Chromatic)

Build UI primitives in isolation, then publish visuals to Chromatic.

```bash
npm run storybook          # http://localhost:6006
npm run build-storybook    # dist/storybook/forjd-ui
npm run chromatic          # needs CHROMATIC_PROJECT_TOKEN
```

Put new stories next to components: `libs/forjd-ui/src/lib/<name>/<name>.stories.ts`.

See `libs/forjd-ui/README.md` for Chromatic first-time setup.
