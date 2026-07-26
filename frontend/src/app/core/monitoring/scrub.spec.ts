import { describe, expect, it } from 'vitest';

import { scrubBreadcrumb, scrubString, scrubValue } from './scrub';

describe('monitoring scrub', () => {
  it('redacts bearer tokens and fjsvc_ values in strings', () => {
    expect(scrubString('Authorization: Bearer abc.def.ghi')).toContain('[Filtered]');
    expect(scrubString('token=fjsvc_ABCDEFGHijklmnop')).toContain('[Filtered]');
  });

  it('filters sensitive object keys', () => {
    const scrubbed = scrubValue({
      authorization: 'Bearer secret',
      tenant_id: 'ok-uuid',
      nested: { cookie: 'a=b', path: '/ready' },
    }) as Record<string, unknown>;
    expect(scrubbed['authorization']).toBe('[Filtered]');
    expect(scrubbed['tenant_id']).toBe('ok-uuid');
    expect((scrubbed['nested'] as Record<string, unknown>)['cookie']).toBe('[Filtered]');
    expect((scrubbed['nested'] as Record<string, unknown>)['path']).toBe('/ready');
  });

  it('filters suffix keys and redis URLs', () => {
    const scrubbed = scrubValue({
      webhook_signing_secret: 'abc',
      access_token: 'xyz',
      note: 'redis://:hunter2@localhost:6379/0',
    }) as Record<string, unknown>;
    expect(scrubbed['webhook_signing_secret']).toBe('[Filtered]');
    expect(scrubbed['access_token']).toBe('[Filtered]');
    expect(scrubbed['note']).toBe('[Filtered]');
  });

  it('scrubs Error message/stack for console bridges', () => {
    const err = new Error('leak Bearer abc.def.ghi');
    const scrubbed = scrubValue(err) as { message: string };
    expect(scrubbed.message).toContain('[Filtered]');
    expect(scrubbed.message).not.toContain('Bearer abc');
  });

  it('scrubs breadcrumb messages and data', () => {
    const safe = scrubBreadcrumb({
      category: 'landing.ready',
      message: 'Bearer leaked.token.value here',
      data: { ciphertext: 'abc', status: 'unreachable' },
    });
    expect(safe.message).toContain('[Filtered]');
    expect(safe.data?.['ciphertext']).toBe('[Filtered]');
    expect(safe.data?.['status']).toBe('unreachable');
  });
});
