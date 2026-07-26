/**
 * Stale-while-revalidate cache with generation-guarded writes.
 * One cache instance per resource (compose; do not build a mega keyed store).
 *
 * ADR: docs/adr/0012-swr-cache-invalidation.md
 */

export type SwrCachePolicy = {
  /** Serve without network when age &lt; freshMs. */
  readonly freshMs: number;
  /** Serve cached value and revalidate in background when freshMs ≤ age &lt; staleMs. */
  readonly staleMs: number;
};

export type SwrReadSource = 'fresh' | 'stale' | 'network';

export type SwrReadResult<T> = {
  readonly value: T;
  readonly source: SwrReadSource;
};

export type CreateSwrCacheOptions<T> = {
  readonly policy: SwrCachePolicy;
  /** Return false to skip storing (e.g. offline). Caller still receives the value. */
  readonly shouldCache?: (value: T) => boolean;
};

export type SwrCache<T> = {
  /** SWR read: fresh hit | stale+background revalidate | blocking network. */
  read(fetcher: () => Promise<T>): Promise<SwrReadResult<T>>;
  /** Hard drop — bump generation so in-flight writes cannot repopulate. */
  invalidate(): void;
  /**
   * Soft invalidate — keep value but age it past `freshMs` so the next `read`
   * returns stale and kicks background revalidation.
   */
  markStale(): void;
  /**
   * Force a background revalidate when a value exists.
   * Failed revalidation keeps the previous value (SWR).
   */
  revalidate(fetcher: () => Promise<T>): Promise<T | null>;
  /** Current value without fetching. */
  peek(): T | null;
  /** Age in ms, or `null` when empty. */
  ageMs(now?: number): number | null;
  /** Notify on successful cache writes (network / revalidate). */
  subscribe(listener: (value: T) => void): () => void;
};

function assertPolicy(policy: SwrCachePolicy): void {
  if (!(policy.freshMs >= 0) || !(policy.staleMs >= policy.freshMs)) {
    throw new Error('SwrCachePolicy: require staleMs >= freshMs >= 0');
  }
}

/**
 * Create a single-resource SWR cache.
 * Prefer one instance per URL/resource over a multi-key global map (ADR-0010).
 */
export function createSwrCache<T>(options: CreateSwrCacheOptions<T>): SwrCache<T> {
  assertPolicy(options.policy);
  const { freshMs, staleMs } = options.policy;
  const shouldCache = options.shouldCache ?? (() => true);

  let value: T | null = null;
  let cachedAt = 0;
  let generation = 0;
  let inflight: Promise<T> | null = null;
  let inflightGen = -1;
  const listeners = new Set<(value: T) => void>();

  function publish(next: T): void {
    for (const listener of listeners) {
      try {
        listener(next);
      } catch {
        // Listener errors must not break cache writes.
      }
    }
  }

  function write(next: T, gen: number): boolean {
    if (gen !== generation) {
      return false;
    }
    if (!shouldCache(next)) {
      return false;
    }
    value = next;
    cachedAt = Date.now();
    publish(next);
    return true;
  }

  function fetchAndStore(fetcher: () => Promise<T>, gen: number): Promise<T> {
    if (inflight && inflightGen === gen) {
      return inflight;
    }
    let promise!: Promise<T>;
    promise = (async () => {
      try {
        const next = await fetcher();
        write(next, gen);
        return next;
      } finally {
        if (inflight === promise) {
          inflight = null;
          inflightGen = -1;
        }
      }
    })();
    inflight = promise;
    inflightGen = gen;
    return promise;
  }

  async function read(fetcher: () => Promise<T>): Promise<SwrReadResult<T>> {
    const now = Date.now();
    const age = value != null ? now - cachedAt : Number.POSITIVE_INFINITY;

    if (value != null && age < freshMs) {
      return { value, source: 'fresh' };
    }

    if (value != null && age < staleMs) {
      const gen = generation;
      void fetchAndStore(fetcher, gen).catch(() => {
        /* keep stale on revalidation failure */
      });
      return { value, source: 'stale' };
    }

    const gen = generation;
    const next = await fetchAndStore(fetcher, gen);
    return { value: next, source: 'network' };
  }

  function invalidate(): void {
    generation += 1;
    value = null;
    cachedAt = 0;
    inflight = null;
    inflightGen = -1;
  }

  function markStale(): void {
    if (value == null) {
      return;
    }
    // Force age >= freshMs while remaining < staleMs when policy allows.
    cachedAt = Date.now() - freshMs;
  }

  async function revalidate(fetcher: () => Promise<T>): Promise<T | null> {
    if (value == null) {
      return null;
    }
    const gen = generation;
    try {
      return await fetchAndStore(fetcher, gen);
    } catch {
      return value;
    }
  }

  function peek(): T | null {
    return value;
  }

  function ageMs(now = Date.now()): number | null {
    if (value == null) {
      return null;
    }
    return Math.max(0, now - cachedAt);
  }

  function subscribe(listener: (value: T) => void): () => void {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }

  return {
    read,
    invalidate,
    markStale,
    revalidate,
    peek,
    ageMs,
    subscribe,
  };
}
