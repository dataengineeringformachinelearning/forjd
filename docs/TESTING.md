# Testing critical paths

Local DX (`doctor`, `quality`, hooks, hot reload): [`DEV.md`](DEV.md).

| Layer | Command | Scope |
|-------|---------|--------|
| Hooks | `npm run install-hooks` | pre-commit: ruff, prettier, typecheck, … |
| Meta (fast) | `npm run quality` (repo root) | Catalog, workflows validate, ruff, prettier, typecheck, suite purity |
| Meta (full) | `npm run quality:full` | Also tests + engine CI-aligned + frontend build |
| Workflows | `npm run validate:workflows` (`--include-examples` in CI) | YAML schema + processor/detector registries ([`EXTENDING.md`](EXTENDING.md)) |
| App unit / integration | `cd frontend && npm run test:app` | Landing, fetch, offline, scrub |
| forjd-ui unit / integration | `cd frontend && npm run test:ui` | Suite stores + prefs/onboarding TestBed |
| Both | `cd frontend && npm run test:all` | CI frontend job |
| E2E | `cd frontend && npm run test:e2e:install && npm run test:e2e` | Landing prefs + onboarding checklist |
| Backend | `cd backend && uv run python -m unittest discover -s tests` | Auth, sealed ingest, audit |

## Suite chrome (ADRs 0024–0027)

- **Unit:** preferences, disclosure (`importMap`), onboarding (`importState`), suite-data-pack (merge/replace/round-trip), activity-log (cap + scrub), search-palette closed-dialog visibility
- **Integration:** `FjPreferencesPanel`, `FjOnboardingChecklist`, `landing.critical.spec.ts`
- **E2E:** `frontend/e2e/landing-critical.spec.ts` (Playwright) — brand/checklist, Preferences → activity, onboarding progress; mocks `/ready` as `{ status: "ready" }`

## Server audit (separate)

- `tests/test_audit.py` — detail sanitizer
- `tests/test_audit_record.py` — `record` / `record_required` insert contract

DEML mirrors suite unit/integration under `packages/viking-ui` (`npm run test:viking-ui`) and app `OnboardingService` specs; Cypress smoke covers public shells including `/account`.
