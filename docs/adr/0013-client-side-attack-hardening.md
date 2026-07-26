# ADR-0013: Client-side attack hardening (XSS, CSRF, open redirects)

## Status

Accepted — 2026-07-26

## Context

FORJD’s browser surface is a **static landing** plus API HTML shells (Swagger/ReDoc).
There is no cookie-session product console. Still, CTAs and suite links must not
become XSS or open-redirect sinks if `apiBaseUrl` or a primitive `href` is
misconfigured. Classic CSRF tokens are the wrong tool for a header-authenticated API.

## Decision

1. **CSRF:** Keep header credentials only (`Authorization` / `X-API-Key`). Do not
   introduce cookie-only write authority. Documented in `backend/docs/AUTH.md`.
2. **XSS (browser):**
   - Landing CSP + hardening headers in `frontend/vercel.json`
     (`frame-ancestors 'none'`, `X-Frame-Options: DENY`, nosniff, COOP, HSTS).
   - API JSON CSP `default-src 'none'`; HTML shells use a narrow allowlist
     (`SecurityHeadersMiddleware`).
   - No `innerHTML` of untrusted content in app code; Angular default escaping.
3. **Open redirects / dangerous URLs:**
   - Shared `safeHref` / `safeHttpBase` in forjd-ui (+ viking-ui dual-adapter).
   - Blocks `javascript:`, `data:`, `vbscript:`, `blob:`, `file:`, protocol-relative
     `//…`, and bare relative paths.
   - `FjButton` / `FjNav` only paint safe hrefs; `_blank` always gets
     `rel="noopener noreferrer"`.
   - Landing suite links pass a host allowlist (`LANDING_LINK_HOSTS`).
4. **Backend redirects:** Do not add open `?next=` / `return_to` redirect helpers
   without an allowlist (none exist today).

## Consequences

- Misconfigured `environment.apiBaseUrl` falls back to `https://backend.forjd.co`
- Unsafe `href` inputs degrade to a non-link button (FjButton) or are dropped (nav)
- CSRF remains “use Bearer / API key”, not synchronizer tokens
