/**
 * Client navigation hygiene — block XSS URL schemes and open redirects.
 * Dual-adapter: keep API aligned with viking-ui/core/safe-href.
 *
 * ADR: docs/adr/0013-client-side-attack-hardening.md
 * ADR: docs/adr/0016-secure-defaults-cookies-headers-api.md
 */

export type SafeHrefOptions = {
  /**
   * When set, absolute `http(s)` URLs must match one of these hosts
   * (exact or subdomain). Relative `/…` and `#…` ignore this list.
   */
  readonly allowedHosts?: readonly string[];
  /**
   * When true, reject `http:` except loopback (`localhost`, `127.0.0.1`, `::1`).
   * Use for API bases so production cannot fall back to cleartext origins.
   */
  readonly httpsOnlyExceptLoopback?: boolean;
};

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '[::1]']);

const CONTROL_CHARS = /[\u0000-\u001F\u007F]/;
const DANGEROUS_SCHEME = /^(javascript|data|vbscript|blob|file):/i;
const HAS_SCHEME = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;

function hostAllowed(hostname: string, allowedHosts: readonly string[]): boolean {
  const host = hostname.toLowerCase();
  return allowedHosts.some((entry) => {
    const allowed = entry.toLowerCase();
    return host === allowed || host.endsWith(`.${allowed}`);
  });
}

/**
 * Return a safe href for `<a>` / button-as-link, or `null` when unsafe.
 *
 * Allows: `https:` / `http:`, `mailto:`, `tel:`, same-origin paths `/…`,
 * in-page hashes `#…`. Blocks: `javascript:`, `data:`, protocol-relative `//…`,
 * control characters, and (when configured) off-allowlist hosts.
 */
export function safeHref(
  raw: string | null | undefined,
  options: SafeHrefOptions = {},
): string | null {
  if (raw == null) {
    return null;
  }
  const href = raw.trim();
  if (!href || CONTROL_CHARS.test(href)) {
    return null;
  }

  // In-page fragment (skip-to-content). Reject embedded schemes.
  if (href.startsWith('#') && !href.includes(':')) {
    return href;
  }

  // Same-origin path — never protocol-relative `//evil.example`.
  if (href.startsWith('/') && !href.startsWith('//')) {
    return href;
  }

  if (href.startsWith('//') || DANGEROUS_SCHEME.test(href)) {
    return null;
  }

  // Bare relative paths (`foo`, `./x`) are easy open-redirect footguns — reject.
  if (!HAS_SCHEME.test(href)) {
    return null;
  }

  let url: URL;
  try {
    url = new URL(href);
  } catch {
    return null;
  }

  const protocol = url.protocol.toLowerCase();
  if (protocol === 'mailto:' || protocol === 'tel:') {
    return href;
  }
  if (protocol !== 'http:' && protocol !== 'https:') {
    return null;
  }

  if (
    protocol === 'http:' &&
    options.httpsOnlyExceptLoopback &&
    !LOOPBACK_HOSTS.has(url.hostname.toLowerCase())
  ) {
    return null;
  }

  if (options.allowedHosts?.length && !hostAllowed(url.hostname, options.allowedHosts)) {
    return null;
  }

  return url.href;
}

/**
 * Normalize an API/origin base to a safe `http(s)` origin+path (no trailing slash).
 * Returns `null` when the value is not a navigable HTTP(S) URL.
 */
export function safeHttpBase(
  raw: string | null | undefined,
  options: SafeHrefOptions = {},
): string | null {
  const href = safeHref(typeof raw === 'string' ? raw.replace(/\/+$/, '') : raw, options);
  if (!href) {
    return null;
  }
  try {
    const url = new URL(href);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return null;
    }
    const path = url.pathname.replace(/\/+$/, '');
    return `${url.origin}${path === '/' ? '' : path}`;
  } catch {
    return null;
  }
}
