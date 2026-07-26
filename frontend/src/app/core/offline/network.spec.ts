import { afterEach, describe, expect, it, vi } from 'vitest';

import { isBrowserOnline, subscribeOnlineStatus } from './network';

describe('network offline helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reads navigator.onLine', () => {
    expect(isBrowserOnline({ onLine: true })).toBe(true);
    expect(isBrowserOnline({ onLine: false })).toBe(false);
  });

  it('defaults to online when navigator is unavailable', () => {
    expect(isBrowserOnline(null)).toBe(true);
  });

  it('subscribes to online/offline events', () => {
    const listeners = new Map<string, EventListener>();
    const target = {
      addEventListener: (type: string, fn: EventListener) => {
        listeners.set(type, fn);
      },
      removeEventListener: (type: string) => {
        listeners.delete(type);
      },
    };
    const listener = vi.fn();
    const unsub = subscribeOnlineStatus(listener, target);
    listeners.get('offline')?.(new Event('offline'));
    listeners.get('online')?.(new Event('online'));
    expect(listener).toHaveBeenNthCalledWith(1, false);
    expect(listener).toHaveBeenNthCalledWith(2, true);
    unsub();
    expect(listeners.size).toBe(0);
  });
});
