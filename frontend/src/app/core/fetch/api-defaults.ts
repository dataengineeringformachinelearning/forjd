/**
 * Secure defaults for browser → API communication.
 * Never send cookies; never widen credentials to `include`.
 *
 * ADR: docs/adr/0016-secure-defaults-cookies-headers-api.md
 */

export const API_FETCH_DEFAULTS = {
  credentials: 'omit',
  headers: {
    Accept: 'application/json',
  },
} as const;

/** Merge caller init onto secure API defaults (credentials always omit). */
export function apiFetchInit(init: RequestInit = {}): RequestInit {
  const mergedHeaders = new Headers(API_FETCH_DEFAULTS.headers);
  if (init.headers) {
    new Headers(init.headers).forEach((value, key) => {
      mergedHeaders.set(key, value);
    });
  }
  return {
    ...init,
    credentials: 'omit',
    headers: mergedHeaders,
  };
}
