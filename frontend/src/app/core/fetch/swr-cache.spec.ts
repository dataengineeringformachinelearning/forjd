import { describe, expect, it, vi } from 'vitest';

import { createSwrCache } from './swr-cache';

describe('createSwrCache', () => {
  it('serves fresh hits without refetch', async () => {
    const cache = createSwrCache<string>({
      policy: { freshMs: 30_000, staleMs: 120_000 },
    });
    const fetcher = vi.fn(async () => 'ok');
    await expect(cache.read(fetcher)).resolves.toEqual({ value: 'ok', source: 'network' });
    await expect(cache.read(fetcher)).resolves.toEqual({ value: 'ok', source: 'fresh' });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('serves stale while revalidating in the background', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-26T15:00:00Z'));
    const cache = createSwrCache<string>({
      policy: { freshMs: 30_000, staleMs: 120_000 },
    });
    const fetcher = vi.fn().mockResolvedValueOnce('v1').mockResolvedValueOnce('v2');

    expect(await cache.read(fetcher)).toEqual({ value: 'v1', source: 'network' });
    vi.setSystemTime(new Date('2026-07-26T15:00:45Z'));
    expect(await cache.read(fetcher)).toEqual({ value: 'v1', source: 'stale' });
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(cache.peek()).toBe('v2');
    vi.useRealTimers();
  });

  it('keeps stale value when background revalidation fails', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-26T15:00:00Z'));
    const cache = createSwrCache<string>({
      policy: { freshMs: 10_000, staleMs: 60_000 },
    });
    const fetcher = vi.fn().mockResolvedValueOnce('v1').mockRejectedValueOnce(new Error('boom'));

    await cache.read(fetcher);
    vi.setSystemTime(new Date('2026-07-26T15:00:20Z'));
    expect(await cache.read(fetcher)).toEqual({ value: 'v1', source: 'stale' });
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(cache.peek()).toBe('v1');
    vi.useRealTimers();
  });

  it('hard invalidate drops value and ignores in-flight writes', async () => {
    const cache = createSwrCache<string>({
      policy: { freshMs: 30_000, staleMs: 120_000 },
    });
    let release!: (value: string) => void;
    const slow = new Promise<string>((resolve) => {
      release = resolve;
    });
    const pending = cache.read(async () => slow);
    cache.invalidate();
    release('late');
    await expect(pending).resolves.toEqual({ value: 'late', source: 'network' });
    expect(cache.peek()).toBeNull();
  });

  it('markStale forces the next read into the revalidate window', async () => {
    const cache = createSwrCache<string>({
      policy: { freshMs: 60_000, staleMs: 120_000 },
    });
    const fetcher = vi.fn().mockResolvedValueOnce('a').mockResolvedValueOnce('b');
    await cache.read(fetcher);
    cache.markStale();
    expect(await cache.read(fetcher)).toEqual({ value: 'a', source: 'stale' });
    await vi.waitFor(() => expect(cache.peek()).toBe('b'));
  });

  it('shouldCache false skips storage (offline-safe)', async () => {
    const cache = createSwrCache<string>({
      policy: { freshMs: 30_000, staleMs: 120_000 },
      shouldCache: (value) => value !== 'offline',
    });
    await expect(cache.read(async () => 'offline')).resolves.toEqual({
      value: 'offline',
      source: 'network',
    });
    expect(cache.peek()).toBeNull();
  });

  it('notifies subscribers only on successful writes', async () => {
    const cache = createSwrCache<string>({
      policy: { freshMs: 30_000, staleMs: 120_000 },
    });
    const seen: string[] = [];
    const unsub = cache.subscribe((value) => {
      seen.push(value);
    });
    await cache.read(async () => 'ok');
    await cache.read(async () => 'ok'); // fresh — no write
    expect(seen).toEqual(['ok']);
    unsub();
    await cache.revalidate(async () => 'next');
    expect(seen).toEqual(['ok']);
  });

  it('dedupes in-flight fetches for the same generation', async () => {
    const cache = createSwrCache<string>({
      policy: { freshMs: 0, staleMs: 0 },
    });
    let release!: (value: string) => void;
    const slow = new Promise<string>((resolve) => {
      release = resolve;
    });
    const fetcher = vi.fn(async () => slow);
    const a = cache.read(fetcher);
    const b = cache.read(fetcher);
    release('once');
    await expect(a).resolves.toEqual({ value: 'once', source: 'network' });
    await expect(b).resolves.toEqual({ value: 'once', source: 'network' });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
