import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  fetchReadyStatus,
  invalidateReadyProbe,
  markReadyProbeStale,
  peekReadyProbe,
  probeApiReady,
  subscribeReadyProbe,
} from './ready-probe';

describe('ready-probe', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-26T15:00:00Z'));
    vi.stubGlobal('navigator', { onLine: true });
  });

  afterEach(() => {
    invalidateReadyProbe();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('returns offline without fetching when the browser is offline', async () => {
    vi.stubGlobal('navigator', { onLine: false });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const onSoftFailure = vi.fn();
    await expect(fetchReadyStatus('http://example.test/ready', { onSoftFailure })).resolves.toBe(
      'offline',
    );
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onSoftFailure).toHaveBeenCalledWith('offline');
  });

  it('maps status ready to ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ status: 'ready' }),
      })),
    );
    await expect(fetchReadyStatus('http://example.test/ready')).resolves.toBe('ok');
  });

  it('maps non-ok HTTP to not_ready and notifies', async () => {
    const onSoftFailure = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 503,
        json: async () => ({}),
      })),
    );
    await expect(fetchReadyStatus('http://example.test/ready', { onSoftFailure })).resolves.toBe(
      'not_ready',
    );
    expect(onSoftFailure).toHaveBeenCalledWith('not_ready', { httpStatus: 503 });
  });

  it('maps network failure to unreachable', async () => {
    const onSoftFailure = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch');
      }),
    );
    await expect(fetchReadyStatus('http://example.test/ready', { onSoftFailure })).resolves.toBe(
      'unreachable',
    );
    expect(onSoftFailure).toHaveBeenCalledWith('unreachable');
  });

  it('returns fresh cache without refetch', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'ready' }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(probeApiReady('http://example.test/ready')).resolves.toBe('ok');
    await expect(probeApiReady('http://example.test/ready')).resolves.toBe('ok');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('serves stale while revalidating', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'ready' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'ready' }),
      });
    vi.stubGlobal('fetch', fetchMock);
    expect(await probeApiReady('http://example.test/ready')).toBe('ok');
    vi.setSystemTime(new Date('2026-07-26T15:00:45Z'));
    expect(await probeApiReady('http://example.test/ready')).toBe('ok');
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('invalidates so the next call refetches', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'ready' }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => ({}),
      });
    vi.stubGlobal('fetch', fetchMock);
    expect(await probeApiReady('http://example.test/ready')).toBe('ok');
    invalidateReadyProbe();
    expect(peekReadyProbe()).toBeNull();
    expect(await probeApiReady('http://example.test/ready')).toBe('not_ready');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('markStale forces background revalidation on the next read', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'ready' }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => ({}),
      });
    vi.stubGlobal('fetch', fetchMock);
    expect(await probeApiReady('http://example.test/ready')).toBe('ok');
    markReadyProbeStale();
    expect(await probeApiReady('http://example.test/ready')).toBe('ok');
    await vi.waitFor(() => expect(peekReadyProbe()).toBe('not_ready'));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('notifies subscribers on cache writes', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'ready' }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    const seen: string[] = [];
    const unsub = subscribeReadyProbe((status) => {
      seen.push(status);
    });
    await probeApiReady('http://example.test/ready');
    expect(seen).toEqual(['ok']);
    unsub();
  });

  it('does not cache offline outcomes', async () => {
    vi.stubGlobal('navigator', { onLine: false });
    vi.stubGlobal('fetch', vi.fn());
    await expect(probeApiReady('http://example.test/ready')).resolves.toBe('offline');
    expect(peekReadyProbe()).toBeNull();
  });
});
