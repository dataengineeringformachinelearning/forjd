# Contributing to FORJD

FORJD is a universal secure streaming engine. Partners integrate via sealed
ingest + tenant-bound `fjsvc_` tokens and YAML workflows — there is no product
console.

## First run

Follow [`docs/START_HERE.md`](docs/START_HERE.md):

```bash
npm run bootstrap
npm run doctor
npm run dev:api    # terminal A
npm run dev:web    # terminal B
npm run verify
```

## Extend / configure

| Goal | Doc / command |
|------|----------------|
| New workflow / detector / add-on | [`docs/EXTENDING.md`](docs/EXTENDING.md) |
| Validate YAML | `npm run validate:workflows` |
| Config inventory | [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) · `config/forjd.catalog.yaml` |
| Auth / tokens | [`backend/docs/AUTH.md`](backend/docs/AUTH.md) |
| Architecture decisions | [`docs/adr/`](docs/adr/README.md) (esp. ADR-0002, ADR-0028) |

Templates: `backend/workflows/examples/`. Do not invent a workflow write API.

## Quality gates

```bash
npm run quality          # catalog + workflows + ruff + prettier + typecheck + suite purity
npm run quality:full     # also tests + engine + frontend build
```

CI: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (includes workflow validation).
Commits: Conventional Commits — [`docs/GIT.md`](docs/GIT.md).

## Security

- Never commit secrets (`.env`, tokens, keys).
- Ciphertext-only sealed lane — processors never open event content (ADR-0002).
- Sole rate limiter: `backend/app/core/rate_limit.py`.
- Report vulnerabilities privately to the maintainers; do not open public issues
  with exploit details.

## Pull requests

Use the PR template. For workflow/detector changes, include
`npm run validate:workflows` (with `--include-examples` if you touched templates)
in the test plan.
