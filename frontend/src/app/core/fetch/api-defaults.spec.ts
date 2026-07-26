import { describe, expect, it } from 'vitest';

import { apiFetchInit } from './api-defaults';

describe('apiFetchInit', () => {
  it('forces credentials omit and Accept json', () => {
    const init = apiFetchInit({
      method: 'GET',
      credentials: 'include',
    });
    expect(init.credentials).toBe('omit');
    expect(new Headers(init.headers).get('Accept')).toBe('application/json');
  });
});
