import { describe, expect, it, vi } from 'vitest';

import { prefersConstrainedDelivery } from './delivery';

describe('prefersConstrainedDelivery', () => {
  it('is false when neither Save-Data nor reduced-data is set', () => {
    const target = {
      matchMedia: vi.fn(() => ({ matches: false })),
      navigator: {},
    };
    expect(prefersConstrainedDelivery(target as never)).toBe(false);
  });

  it('is true for prefers-reduced-data', () => {
    const target = {
      matchMedia: vi.fn((query: string) => ({
        matches: query.includes('prefers-reduced-data'),
      })),
      navigator: {},
    };
    expect(prefersConstrainedDelivery(target as never)).toBe(true);
  });

  it('is true for navigator.connection.saveData', () => {
    const target = {
      matchMedia: vi.fn(() => ({ matches: false })),
      navigator: { connection: { saveData: true } },
    };
    expect(prefersConstrainedDelivery(target as never)).toBe(true);
  });
});
