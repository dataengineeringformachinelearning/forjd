# ADR-0018: Defensive outbound HTTP and unexpected data shapes

## Status

Accepted — 2026-07-26

## Context

Third-party APIs (crt.sh, HIBP, OSV, HoneyDB, TAXII, engine HTTP) can return
oversized bodies, non-JSON, redirects, or unexpected shapes. Fetchers already
used soft `FetchResult` envelopes and `sanitize_external` (ADR-0014); TAXII had
streamed byte caps. Other clients still called unbounded `.json()`.

## Decision

1. **Shared helper** — `app/core/outbound_http.py`:
   - Timeouts with bounded connect
   - `follow_redirects=False`
   - Streamed body cap (`DEFAULT_MAX_RESPONSE_BYTES` = 2 MiB)
   - JSON decode → optional `sanitize_external`
   - Shape guards: `expect_dict` / `expect_list` / `expect_list_of_dicts`
   - `OutboundHttpError` for soft envelopes (no raw body echo)
2. **Wire first** — fetchers, add-on clients, engine JSON decode, TAXII read.
3. **Frontend** — `parseResponseJson` maps malformed JSON to soft failure
   (ready-probe → `unreachable`).
4. **Do not** invent a second rate limiter for outbound (ADR-0015); do not
   invent a parallel sanitizer (ADR-0014 / 0017).

## Consequences

- Prefer `request_json` / `parse_response_content` for new outbound JSON
- Soft `{ok:false}` / `FetchResult` over raised stack traces to callers
- Ciphertext lanes stay opaque; never log raw third-party bodies
