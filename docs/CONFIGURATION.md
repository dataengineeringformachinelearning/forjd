# FORJD configuration

Single source of truth for **what can be configured**, **where it lives**, and
**which knobs are feature flags**.

**ADR:** [`adr/0004-config-catalog-inventory-sot.md`](adr/0004-config-catalog-inventory-sot.md).

| Concern | Authority |
|---------|-----------|
| Inventory (names, layers, secrecy, flags) | [`config/forjd.catalog.yaml`](../config/forjd.catalog.yaml) |
| Backend typed defaults / parsing | [`backend/app/core/config.py`](../backend/app/core/config.py) `Settings` |
| Backend feature-flag view | [`backend/app/core/feature_flags.py`](../backend/app/core/feature_flags.py) |
| Engine runtime | `FORJD_ROLE` + [`engine/src/data_plane/config.rs`](../engine/src/data_plane/config.rs) |
| Frontend (landing) | [`frontend/src/environments/`](../frontend/src/environments/) |
| Local examples | `backend/.env.example`, `engine/.env.example` |
| Drift gate | `python scripts/check_config_catalog.py` |

Do **not** invent a second settings system, a second rate limiter, or ad-hoc
`os.environ` reads for values already on `Settings`.

## Layers

```
config/forjd.catalog.yaml     ← inventory SoT (this doc’s index)
        │
        ├─ backend Settings   ← runtime SoT (Pydantic)
        ├─ engine Config      ← runtime SoT (Rust env)
        └─ environment*.ts    ← runtime SoT (Angular fileReplacements)
```

Secrets are never returned by the API. Public introspection:

- Feature add-ons → `GET /api/v1/addons`
- Partner route contract → `GET /api/v1/capabilities`
- Observability sinks → [`OBSERVABILITY.md`](OBSERVABILITY.md)

## Feature flags

Declared under `feature_flags:` in the catalog. Patterns:

| Pattern | Examples |
|---------|----------|
| Empty string / token disables | `ROLLBAR_ACCESS_TOKEN`, `SENTRY_DSN`, `API_KEY`, `ENGINE_URL` |
| Explicit bool | `RATE_LIMIT_ENABLED`, `ENABLE_API_DOCS`, `REQUIRE_RLS`, `WORKFLOWS_STRICT` |
| Comma catalog / `all` | `FORJD_ADDONS` (+ optional `FORJD_ADDONS_CONFIG` YAML) |
| Interval `0` disables worker | `ANALYTICS_ROLLUP_INTERVAL_SECONDS`, `TRAINING_TICK_SECONDS`, `RETENTION_SWEEP_INTERVAL_SECONDS` |
| Engine role | `FORJD_ROLE` (`engine` = HTTP only; `all` = data plane) |

Production fail-closed (`ENVIRONMENT` ∈ production/prod/staging/stage **or**
`FLY_APP_NAME` set): `DEBUG=false`, `SOFT_MIGRATE_SCHEMA=false`,
`REQUIRE_RLS=true`, `REQUIRE_CRYPTO_SESSION=true`, docs off unless
`ENABLE_API_DOCS` is explicitly in the process environment.

Engine production gate uses **`FORJD_ENV=production`** (or Fly) — distinct from
backend `ENVIRONMENT`. Both are catalogued; do not conflate them.

## Adding a new setting

1. Add the field to the correct runtime owner (`Settings`, Rust env, or
   `environment*.ts`).
2. Add a row to `config/forjd.catalog.yaml` (`settings: true` for backend).
3. If it is a gate, also list it under `feature_flags:`.
4. Document a safe default in the matching `.env.example` (or frontend file).
5. Run `uv run --project backend python scripts/check_config_catalog.py`.

## Operator quick map

| Deploy surface | Non-secret defaults | Secrets |
|----------------|---------------------|---------|
| API Fly | `fly.api.toml` `[env]` | `fly secrets` (see [`PRODUCTION_DEPLOY.md`](PRODUCTION_DEPLOY.md)) |
| Engine Fly | `engine/fly.toml` `[env]` | `DATABASE_URL` / `REDIS_URL` / `ENGINE_API_TOKEN` / `FORJD_INTERNODE_*` |
| Dragonfly | `infra/dragonfly/fly.toml` | `DFLY_requirepass` |
| Vercel landing | `environment.ts` | none (client DSN/tokens are public by design) |
| Local Chromatic | root `.env` | `CHROMATIC_PROJECT_TOKEN` |

## Related

- Auth principals → [`backend/docs/AUTH.md`](../backend/docs/AUTH.md)
- Extending workflows / detectors → [`EXTENDING.md`](EXTENDING.md) (`npm run validate:workflows`)
- Add-on profiles → [`backend/docs/ADDONS.md`](../backend/docs/ADDONS.md)
- Scale / deferred knobs → [`SCALE.md`](SCALE.md) (ideas there are **not** live until they appear in the catalog + `Settings`)
