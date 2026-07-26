/**
 * FORJD `/ready` continuity probe — domain/infra, not UI.
 * Landing binds the settled status; forjd-ui never imports this module.
 *
 * Uses `createSwrCache` (fresh / stale-while-revalidate / hard invalidate).
 * Offline is never cached — see ADR-0009 / ADR-0012.
 */

import { apiFetchInit } from '../fetch/api-defaults';
import { parseResponseJson } from '../fetch/parse-json';
import { createSwrCache } from '../fetch/swr-cache';
import { isBrowserOnline } from '../offline/network';

export type ReadyProbeStatus = 'ok' | 'not_ready' | 'unreachable' | 'offline' | 'checking';
export type ReadyProbeSettled = Exclude<ReadyProbeStatus, 'checking'>;
export type ReadyProbeSoftFailure = Exclude<ReadyProbeSettled, 'ok'>;

/** Flat soft-failure extras — avoid Record nesting in hooks. */
export type ReadyProbeFailureData = {
  readonly httpStatus?: number;
  readonly reportedStatus?: string;
};

type ReadyResponseBody = {
  status?: string;
};

export type ReadyProbeHooks = {
  /** Soft failures only — never include tokens or ciphertext. */
  onSoftFailure?: (outcome: ReadyProbeSoftFailure, data?: ReadyProbeFailureData) => void;
};

const READY_TIMEOUT_MS = 2_500;

/** Public policy — fresh serve, then SWR, then blocking miss. */
export const READY_CACHE_POLICY = {
  freshMs: 30_000,
  staleMs: 2 * 60_000,
} as const;

// --- Single-resource SWR cache for /ready ---
const readyCache = createSwrCache<ReadyProbeSettled>({
  policy: READY_CACHE_POLICY,
  shouldCache: (status) => status !== 'offline',
});

function isReadyResponseBody(value: unknown): value is ReadyResponseBody {
  return typeof value === 'object' && value !== null;
}

/** Map a single HTTP response to a settled probe status (no cache). */
export async function fetchReadyStatus(
  readyUrl: string,
  options: { signal?: AbortSignal; onSoftFailure?: ReadyProbeHooks['onSoftFailure'] } = {},
): Promise<ReadyProbeSettled> {
  const { signal, onSoftFailure } = options;
  if (!isBrowserOnline()) {
    onSoftFailure?.('offline');
    return 'offline';
  }
  try {
    const response = await fetch(
      readyUrl,
      apiFetchInit({
        method: 'GET',
        signal,
      }),
    );
    if (!response.ok) {
      onSoftFailure?.('not_ready', { httpStatus: response.status });
      return 'not_ready';
    }
    const parsed = await parseResponseJson(response);
    if (!parsed.ok) {
      onSoftFailure?.('unreachable');
      return 'unreachable';
    }
    const statusText = isReadyResponseBody(parsed.value) ? parsed.value.status : undefined;
    if ((statusText || '').toLowerCase() === 'ready') {
      return 'ok';
    }
    onSoftFailure?.('not_ready', { reportedStatus: statusText ?? 'unknown' });
    return 'not_ready';
  } catch {
    if (!isBrowserOnline()) {
      onSoftFailure?.('offline');
      return 'offline';
    }
    onSoftFailure?.('unreachable');
    return 'unreachable';
  }
}

function fetchReadyWithTimeout(
  readyUrl: string,
  hooks: ReadyProbeHooks,
): Promise<ReadyProbeSettled> {
  return (async () => {
    const controller = new AbortController();
    const timer = globalThis.setTimeout(() => controller.abort(), READY_TIMEOUT_MS);
    try {
      return await fetchReadyStatus(readyUrl, {
        signal: controller.signal,
        onSoftFailure: hooks.onSoftFailure,
      });
    } finally {
      globalThis.clearTimeout(timer);
    }
  })();
}

/** Cached `/ready` probe used by the public landing (SWR). */
export async function probeApiReady(
  readyUrl: string,
  hooks: ReadyProbeHooks = {},
): Promise<ReadyProbeSettled> {
  if (!isBrowserOnline()) {
    hooks.onSoftFailure?.('offline');
    return 'offline';
  }
  const { value } = await readyCache.read(() => fetchReadyWithTimeout(readyUrl, hooks));
  return value;
}

/** Hard invalidate — next probe is a blocking network read (Retry). */
export function invalidateReadyProbe(): void {
  readyCache.invalidate();
}

/**
 * Soft invalidate — keep last status but force background revalidation on next read
 * (e.g. tab focus / visibility).
 */
export function markReadyProbeStale(): void {
  readyCache.markStale();
}

/** Force background revalidation when a cached value exists. */
export async function revalidateReadyProbe(
  readyUrl: string,
  hooks: ReadyProbeHooks = {},
): Promise<ReadyProbeSettled | null> {
  if (!isBrowserOnline()) {
    return null;
  }
  return readyCache.revalidate(() => fetchReadyWithTimeout(readyUrl, hooks));
}

/** Subscribe to successful cache writes (SWR background updates). */
export function subscribeReadyProbe(listener: (status: ReadyProbeSettled) => void): () => void {
  return readyCache.subscribe(listener);
}

/** Test / diagnostics — current cached value without fetching. */
export function peekReadyProbe(): ReadyProbeSettled | null {
  return readyCache.peek();
}

/** Age of the cached probe in ms, or `null` when empty. */
export function readyProbeAgeMs(now?: number): number | null {
  return readyCache.ageMs(now);
}
