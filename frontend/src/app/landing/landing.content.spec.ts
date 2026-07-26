import { describe, expect, it } from 'vitest';

import { landingReadyStory, landingSuiteLinks } from './landing.content';

describe('landingSuiteLinks', () => {
  it('builds suite URLs from a trusted API base', () => {
    const links = landingSuiteLinks('https://backend.forjd.co');
    expect(links.docsUrl).toContain('/docs');
    expect(links.readyUrl).toContain('/ready');
    expect(links.privacyUrl).toContain('privacy');
  });

  it('rejects dangerous apiBaseUrl values (open redirect / XSS)', () => {
    const links = landingSuiteLinks('javascript:alert(1)');
    expect(links.apiBaseUrl).toBe('https://backend.forjd.co');
    expect(links.docsUrl.startsWith('https://')).toBe(true);
    expect(links.docsUrl.toLowerCase()).not.toContain('javascript:');
  });

  it('rejects off-allowlist hosts', () => {
    const links = landingSuiteLinks('https://evil.example');
    expect(links.apiBaseUrl).toBe('https://backend.forjd.co');
  });
});

describe('landingReadyStory', () => {
  it('tells Confirming → ready → degraded as one product voice', () => {
    expect(landingReadyStory({ loading: true, error: null })).toMatchObject({
      phase: 'loading',
      suffix: 'Confirming',
      detail: null,
      retryLabel: null,
    });
    expect(landingReadyStory({ loading: false, error: null })).toMatchObject({
      phase: 'ready',
      suffix: null,
      detail: null,
    });
    expect(landingReadyStory({ loading: false, error: 'offline' })).toMatchObject({
      phase: 'degraded',
      suffix: 'Offline',
      tone: 'warning',
      retryLabel: 'Try again',
    });
    expect(landingReadyStory({ loading: false, error: 'unreachable' })).toMatchObject({
      phase: 'degraded',
      suffix: 'Unavailable',
      tone: 'danger',
    });
    expect(landingReadyStory({ loading: false, error: 'not_ready' }).detail).toMatch(
      /sealed ingest/i,
    );
  });
});
