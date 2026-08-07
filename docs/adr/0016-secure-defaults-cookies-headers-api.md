# ADR-0016: Secure defaults for cookies, headers, and API communication

## Status

Accepted — 2026-07-26

## Context

FORJD is header-authenticated ([`backend/docs/AUTH.md`](../../backend/docs/AUTH.md)).
Session cookies must not appear as a second write path. Security headers already
exist on the API; the engine and edge were thinner. Production CORS must stay an
exact HTTPS allowlist. There is no product SPA.

## Decision

1. **Cookies** — FORJD sets **no session cookies**. Auth remains
   `Authorization` / `X-API-Key`. If a non-auth cookie is ever needed, use
   `app/core/cookies.build_set_cookie` (Secure in production, HttpOnly default,
   SameSite=Lax; `SameSite=None` requires Secure). Do not invent CSRF cookie
   tokens.
2. **Headers** — Keep `SecurityHeadersMiddleware` as the API baseline. Engine and
   `peer-sessions` edge align with API hardening (CSP `default-src 'none'`,
   COOP/CORP, Permissions-Policy, HSTS when production/HTTPS). HTML shells use a
   narrower CSP for self-hosted static assets.
3. **API communication** — Production CORS rejects `*` and requires at least one
   `https://` origin. Production HTTP (via `X-Forwarded-Proto`) receives a 308
   redirect to HTTPS. Partner BFFs own browser credential policy.

## Consequences

- Do not add cookie-session SPA auth on FORJD hosts
- Do not set `allow_credentials=True` with wildcard CORS
- Rate limiting stays sole-owned in `rate_limit.py` (ADR-0007 / ADR-0015)
- Analytics vendor cookies on the splash remain vendor-owned, not FORJD session authority
