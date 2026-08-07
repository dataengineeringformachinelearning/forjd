# ADR-0015: Rate limiting, input validation, and output encoding

## Status

Accepted — 2026-07-26

## Context

Partners hammer public and auth surfaces; free-text fields reach APIs, PDFs, and
status pages. Rate limiting must stay sole-owned (`rate_limit.py` / ADR-0007).
Input sanitization (ADR-0014) was incomplete on SIEM/report length caps and some
domain models. Output sinks differ: JSON (serializer), HTML shells, PDF literals.

## Decision

1. **Rate limiting** — extend the existing sole limiter only:
   - Public IP allowlist includes `GET /addons/{slug}` (prefix `/addons/`).
   - Missing-Bearer `401`s share the `auth-failure` IP bucket with bad tokens.
   - `/health` and `/ready` remain unrestricted ops probes.
2. **Input validation** — Pydantic + `text_fields` / `sanitize_*`:
   - `_reject_sensitive_text` honors per-field `max_length` (summary 2048, body
     8000, titles 255; metadata stays 512).
   - Slugs use `Slug64` / `AddonSlug`; remaining UGC (tenant name, report title,
     honeypot strings, alert titles) use sanitize presets.
   - `RequestValidationError` handler returns `loc`/`type`/`msg` and **drops**
     request `input` echoes.
3. **Output encoding** — context helpers in `app/core/encoding.py`:
   - JSON: Starlette/FastAPI serialization (no HTML context).
   - HTML shells: `encode_html_text` (after sanitize).
   - PDF: `encode_pdf_literal` for `(…) Tj` / Info strings.
   - Partner UIs own template auto-escape; never raw HTML for UGC.

## Consequences

- Do not add SlowAPI / a second Redis limiter class
- Do not introduce HTML/markdown UGC rendering without a dedicated sanitizer ADR
- Ciphertext envelopes stay opaque — never pass through sanitize/encode helpers
