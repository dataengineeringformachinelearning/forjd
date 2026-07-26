# Security policy

## Reporting

Report suspected vulnerabilities privately to the maintainers. Do not open
public issues with exploit PoCs or secrets.

## Invariants (do not break)

| Invariant | Reference |
|-----------|-----------|
| Ciphertext-only sealed lane | ADR-0002 · `ARCHITECTURE.md` |
| Partner `fjsvc_` only — no end-user tokens at the edge | `backend/docs/AUTH.md` |
| Tenant isolation (RLS + `require_tenant_access`) | `ARCHITECTURE.md` |
| Sole rate limiter (`rate_limit.py`) | ADR-0007 · ADR-0015 |
| No secrets in git | ADR-0017 · `.env.example` only |
| Workflow YAML SoT — no partner write API | ADR-0028 · `docs/EXTENDING.md` |

## Automated gates

- Semgrep (Cursor / CI policy), Trivy/gitleaks where configured in the suite
- `npm run validate:workflows` — unknown processors/steps fail CI (typos cannot ship silently)
- Optional runtime: `WORKFLOWS_STRICT=true`
- Config catalog drift: `scripts/check_config_catalog.py`

## Dependency updates

Upgrade one major component at a time (`uv lock --upgrade` / npm), then run
`npm run quality` / `quality:full`. Prefer stability over bleeding-edge majors
(Python **3.12**, Arrow pin notes in `.cursorrules`).
