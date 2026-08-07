# ADR-0005: Correlation-first observability (no second metrics stack)

## Status

Accepted — 2026-07-26

## Context

Operators need joinable logs across API → engine → workers. Full APM, OTLP, and
Prometheus were proposed early; cost and operational load are not justified at
current scale (`docs/SCALE.md`).

## Decision

Ship **correlation + structured logs + optional error trackers** first:

1. Validate/echo/generate `X-Request-ID`; bind ContextVars; JSON log fields
2. Unhandled `500` bodies include `request_id` (no internals in production)
3. Outbound engine HTTP forwards `X-Request-ID`
4. Rollbar (API) + optional Sentry; empty token/DSN disables
5. Workers emit `worker_tick` extras (`duration_ms`, `outcome`) — not a second
   metrics daemon
6. Server scrub via `sanitize.scrub_for_logs` before tracker payloads leave the process

**Deferred:** `/metrics`, OTLP collectors, second rate/metrics libraries.

## Consequences

- Prefer log-derived RED signals before adding Prometheus
- Never log ciphertext, `Authorization`, or `fjsvc_` values
- Contract: `docs/OBSERVABILITY.md`
