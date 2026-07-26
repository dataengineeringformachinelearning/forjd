import { describe, expect, it } from 'vitest';

import { isChunkLoadError } from './chunk-load-recovery';

describe('isChunkLoadError', () => {
  it('detects Angular dynamic import failures', () => {
    expect(
      isChunkLoadError(
        new TypeError('Failed to fetch dynamically imported module: https://forjd.co/chunk-x.js'),
      ),
    ).toBe(true);
    expect(isChunkLoadError(new Error('Importing a module script failed.'))).toBe(true);
  });

  it('ignores unrelated errors', () => {
    expect(isChunkLoadError(new Error('Http failure response for /api: 503'))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});
