import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { shouldRefreshLandingReadyOnVisible } from './landing-ready';
import { invalidateReadyProbe, probeApiReady } from './ready-probe';

describe('shouldRefreshLandingReadyOnVisible', () => {
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

  it('refreshes when the cache is empty', () => {
    expect(shouldRefreshLandingReadyOnVisible()).toBe(true);
  });

  it('skips while the probe is still fresh', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ status: 'ready' }),
      })),
    );
    await probeApiReady('http://example.test/ready');
    expect(shouldRefreshLandingReadyOnVisible()).toBe(false);
    vi.setSystemTime(new Date('2026-07-26T15:00:45Z'));
    expect(shouldRefreshLandingReadyOnVisible()).toBe(true);
  });
});
