import { describe, expect, it } from 'vitest';

import { safeHref, safeHttpBase } from './safe-href';

describe('safeHref', () => {
  it('allows https, relative paths, and hash fragments', () => {
    expect(safeHref('https://backend.forjd.co/docs')).toBe('https://backend.forjd.co/docs');
    expect(safeHref('/ready')).toBe('/ready');
    expect(safeHref('#main-content')).toBe('#main-content');
  });

  it('blocks XSS schemes and protocol-relative URLs', () => {
    expect(safeHref('javascript:alert(1)')).toBeNull();
    expect(safeHref('JavaScript:alert(1)')).toBeNull();
    expect(safeHref('data:text/html,<script>')).toBeNull();
    expect(safeHref('vbscript:msgbox(1)')).toBeNull();
    expect(safeHref('//evil.example/phish')).toBeNull();
    expect(safeHref('  javascript:alert(1)  ')).toBeNull();
  });

  it('blocks bare relative open-redirect footguns', () => {
    expect(safeHref('evil.example/path')).toBeNull();
    expect(safeHref('./escape')).toBeNull();
  });

  it('enforces an optional host allowlist', () => {
    expect(
      safeHref('https://backend.forjd.co/docs', {
        allowedHosts: ['forjd.co', 'backend.forjd.co'],
      }),
    ).toBe('https://backend.forjd.co/docs');
    expect(
      safeHref('https://evil.example/docs', {
        allowedHosts: ['forjd.co'],
      }),
    ).toBeNull();
    expect(
      safeHref('https://api.forjd.co/ready', {
        allowedHosts: ['forjd.co'],
      }),
    ).toBe('https://api.forjd.co/ready');
  });

  it('allows mailto and tel', () => {
    expect(safeHref('mailto:ops@forjd.co')).toBe('mailto:ops@forjd.co');
    expect(safeHref('tel:+15551212')).toBe('tel:+15551212');
  });
});

describe('safeHttpBase', () => {
  it('strips trailing slashes and rejects non-http', () => {
    expect(safeHttpBase('https://backend.forjd.co/')).toBe('https://backend.forjd.co');
    expect(safeHttpBase('javascript:alert(1)')).toBeNull();
    expect(
      safeHttpBase('http://127.0.0.1:8000', { allowedHosts: ['127.0.0.1', 'localhost'] }),
    ).toBe('http://127.0.0.1:8000');
  });

  it('rejects non-loopback http when httpsOnlyExceptLoopback', () => {
    expect(
      safeHttpBase('http://evil.example', {
        httpsOnlyExceptLoopback: true,
        allowedHosts: ['evil.example'],
      }),
    ).toBeNull();
    expect(
      safeHttpBase('http://localhost:8000', {
        httpsOnlyExceptLoopback: true,
        allowedHosts: ['localhost'],
      }),
    ).toBe('http://localhost:8000');
  });
});
