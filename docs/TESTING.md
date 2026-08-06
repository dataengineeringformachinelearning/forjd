# Testing critical paths

Local DX (`doctor`, `quality`, hooks): [`DEV.md`](DEV.md).

| Layer | Command | Scope |
|-------|---------|--------|
| Hooks | `npm run install-hooks` | pre-commit quality |
| Meta (fast) | `npm run quality` | Catalog, workflows, ruff |
| Meta (full) | `npm run quality:full` | Also tests + engine clippy (CI-aligned) |
| Workflows | `npm run validate:workflows` | YAML schema + registries ([`EXTENDING.md`](EXTENDING.md)) |
| Backend | `cd backend && uv run python -m unittest discover -s tests` | Auth, sealed ingest, audit |
| deml-ui sync | `npm run sync:deml-ui` · `npm run doctor` | Vendored CSS present |

## Server audit

- `tests/test_audit.py` — detail sanitizer
- `tests/test_audit_record.py` — `record` / `record_required` insert contract

## Retired

Angular landing / forjd-ui Storybook / Playwright frontend jobs are **removed**.
Product UI tests live in the `deml` and `deml-ui` repositories.
