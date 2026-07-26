# ADR-0017: Secrets and sensitive data (client + server)

## Status

Accepted — 2026-07-26

## Context

Tokens (`fjsvc_`, Bearer, JWT), ciphertext, and DB/cache URLs can appear in
exception text, structured logs, and error trackers. Scrubbing already existed
for Sentry (`scrub_for_logs` / `scrub.ts`) and 422 input stripping (ADR-0015),
but stdout JSON logs and Rollbar used weaker key-only scrubbing. Ciphertext
envelopes must stay opaque (ADR-0002); the browser must never hold `fjsvc_`.

## Decision

1. **One scrub family** — extend `sanitize.scrub_for_logs` / `scrub.ts` (keep
   patterns in lockstep). Do not invent a parallel redaction library.
2. **Stdout JSON** — `JsonFormatter` deep-scrubs every log payload before emit.
3. **Trackers** — Sentry `before_send` and Rollbar `_build_payload` both run
   `scrub_for_logs` / `scrubValue`.
4. **Client console** — `GlobalErrorHandler`, monitoring init failures, and
   bootstrap errors log `scrubValue(...)` so console→tracker bridges stay clean.
5. **Never in browser** — `fjsvc_`, provision tokens, JWT secrets, engine tokens.
   Client DSNs are public ingest endpoints, not service credentials.
6. **Never log** — sealed ciphertext, Authorization/cookies, crypto keys,
   webhook HMAC secrets, partner end-user tokens (see OBSERVABILITY.md).

## Consequences

- Widen key/value patterns carefully; prefer false-positive filter over leak
- Ciphertext fields are filtered by key — never decrypt for logging
- Cookie CSRF and second rate limiters remain out of scope (ADR-0013 / 0015)
