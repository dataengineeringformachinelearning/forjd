# ADR-0014: Sanitize UGC and third-party data

## Status

Accepted — 2026-07-26

## Context

FORJD accepts partner-authored plain text (status pages, cases, playbooks) and
pulls third-party OSINT JSON (HIBP, crt.sh, …). There is no HTML product console
on forjd.co, but stored strings still reach APIs, PDFs, public status KPIs, and
observability pipelines. Ciphertext envelopes must remain untouched.

## Decision

1. **Central helpers** in `app/core/sanitize.py`:
   - `sanitize_text` / `sanitize_label` / `sanitize_body` — NFC, unescape, strip
     tags/controls, length bounds (plain text only).
   - `sanitize_external` — recursive third-party JSON with depth/list/key caps;
     secret-shaped keys → `[Filtered]`.
   - `scrub_for_logs` — deep secret/ciphertext scrub for Sentry (mirrors
     frontend `scrub.ts`).
2. **Pydantic presets** in `app/core/text_fields.py` (`Title200`, `Description4k`,
   …) applied to status, domain, service-account, and partner provision fields.
3. **Fetchers** sanitize after transform (`Fetcher.sanitize_data` +
   `FetchResult.to_dict`).
4. **Stream routing tags** pass through `sanitize_label` (never ciphertext).
5. **Frontend** exports `sanitizeDisplayText` (forjd-ui / viking-ui) for any
   future bind of third-party strings; Angular escaping remains the last line.

## Consequences

- HTML in UGC is stripped at the edge, not rendered
- Mis-sized third-party blobs are truncated instead of stored whole
- Do not introduce a HTML/markdown rendering pipeline without a dedicated
  sanitizer (DOMPurify / bleach) review
- Sealed `ciphertext` fields are never passed through these helpers
