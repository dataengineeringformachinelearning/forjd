# FORJD observability

Runtime logging and error reporting for the data plane. Suite design CI purity
is **not** covered here (see `docs/SUITE_UI_UNIFICATION*.md`).

**ADR:** [`adr/0005-observability-correlation-first.md`](adr/0005-observability-correlation-first.md).

## Layers (do not invent a second stack)

| Layer | What | Gate |
|-------|------|------|
| Probes | `GET /health`, `GET /ready`, engine role-aware `/ready` | Always on |
| Structured logs | JSON stdout (`backend/app/core/logging.py`); Rust `tracing` JSON | Always on |
| Correlation | `X-Request-ID` (validate/echo/generate) → log fields → 500 body → engine HTTP | Always on |
| Error trackers | Rollbar (API + browser); optional Sentry (`SENTRY_DSN`, `uv sync --group sentry`) | Empty token/DSN disables |
| Product analytics | Vercel Analytics / Speed Insights; GA4 + Clarity on landing | Frontend / marketing only |
| Rate limiting | Sole implementation: `app/core/rate_limit.py` | Config-gated |

**Deferred until load warrants** (see `docs/SCALE.md`): thin RED metrics /
`/metrics`. Prefer log-derived counters from `request_completed` before adding
Prometheus.

**Parked:** engine OTLP crates remain optional/unused until an explicit
collector + cost decision.

## Correlation contract

1. Client or partner BFF **may** send `X-Request-ID` (`[A-Za-z0-9][A-Za-z0-9._-]{7,127}`).
2. API middleware validates or generates a UUID hex id, binds ContextVars, echoes
   the header, and attaches `Server-Timing`.
3. JSON logs include `request_id`, `principal_kind`, `principal_id`, `tenant_id`
   (never tokens or ciphertext).
4. Unhandled `500` responses include `request_id` in the JSON body for support.
5. Outbound engine HTTP (`ENGINE_URL`) forwards `X-Request-ID` so API ↔ engine
   logs join on the same id.

## Never log or send to trackers

- Sealed ciphertext / envelope payloads
- `Authorization`, cookies, `fjsvc_` / JWT values
- Crypto session keys, webhook signing secrets
- End-user partner tokens (Firebase / `deml_`)
- Postgres/Redis URLs that embed passwords

**ADR:** [`adr/0017-secrets-and-sensitive-data.md`](adr/0017-secrets-and-sensitive-data.md).

Client scrub helpers live in `frontend/src/app/core/monitoring/scrub.ts`
(`beforeSend` / Rollbar `transform` / scrubbed `console.error`). Server:

- JSON stdout: `JsonFormatter` → `scrub_for_logs` on every line
- Sentry: `send_default_pii=False` + `before_send` → `scrub_for_logs`
- Rollbar: expanded `scrub_fields` + deep scrub on `_build_payload`

Unhandled API 500s also tag Sentry `request_id`. Patterns stay in lockstep
between `sanitize.py` and `scrub.ts`.

## Backend

- Bootstrap: `configure_logging` → `configure_sentry` → `configure_rollbar` in
  `app/main.py`.
- Request middleware: `RequestContextMiddleware` (`app/core/request_context.py`).
- Workers: use `app/core/worker_logging.py` extras (`worker`, `duration_ms`,
  `outcome`) on tick boundaries; health via `WorkerHealthRegistry`.

## Frontend (landing)

- Idle-init Sentry + Rollbar via `monitoring.facade.ts`.
- `GlobalErrorHandler`: chunk one-shot reload, danger toast, then capture.
- Breadcrumbs for soft failures (e.g. `/ready` probe) — not dual console storms.
- Storybook: **no** third-party analytics or Sentry (see `.storybook/`).

## Engine (Rust)

- `tracing_subscriber` JSON + `EnvFilter`; `tower_http` request-id layers.
- `/health` + role-aware `/ready`; probe roles persist
  `health_probe_observations`.
- No `/metrics` yet; keep OTLP dormant.

## Operator quick checks

```bash
curl -fsS https://backend.forjd.co/health
curl -fsS https://backend.forjd.co/ready
curl -sI -H 'X-Request-ID: deml_01J7ABCD12345678' https://backend.forjd.co/health | grep -i x-request-id
./scripts/verify_stack_health.sh
```

Empty `ROLLBAR_ACCESS_TOKEN` / `SENTRY_DSN` disables those sinks locally and in
CI without code changes.
