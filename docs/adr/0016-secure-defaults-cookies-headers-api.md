# ADR-0016: Secure defaults for cookies, headers, and API communication

## Status

Accepted — 2026-07-26

## Context

FORJD is header-authenticated (ADR-0013). Session cookies must not appear as a
second write path. Security headers already exist on the API and Vercel landing;
the engine and edge were thinner. Browser API calls must never send cookies
(`credentials: 'include'`), and production CORS must stay an exact HTTPS
allowlist.

## Decision

1. **Cookies** — FORJD sets **no session cookies**. Auth remains
   `Authorization` / `X-API-Key`. If a non-auth cookie is ever needed, use
   `app/core/cookies.build_set_cookie` (Secure in production, HttpOnly default,
   SameSite=Lax; `SameSite=None` requires Secure). Do not invent CSRF cookie
   tokens.
2. **Headers** — Keep `SecurityHeadersMiddleware` as the API baseline. Landing
   Vercel adds `Cross-Origin-Resource-Policy`. Engine and `peer-sessions` edge
   align with API hardening (CSP `default-src 'none'`, COOP/CORP, Permissions-Policy,
   HSTS when production/HTTPS).
3. **API communication** — Browser fetches use `credentials: 'omit'` via
   `apiFetchInit`. `safeHttpBase` rejects non-loopback `http:` when
   `httpsOnlyExceptLoopback` is set. Production CORS rejects `*` and requires
   at least one `https://` origin. Production HTTP (via `X-Forwarded-Proto`)
   receives a 308 redirect to HTTPS.

## Consequences

- Do not add cookie-session SPA auth on forjd.co
- Do not set `allow_credentials=True` with wildcard CORS
- Rate limiting stays sole-owned in `rate_limit.py` (ADR-0007 / ADR-0015)
- Analytics vendor cookies (gtag SameSite=None;Secure;Partitioned) remain
  vendor-owned, not FORJD session authority
