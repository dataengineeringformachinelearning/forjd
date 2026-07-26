import { describe, expect, it } from 'vitest';

import { encodeForHtml, sanitizeDisplayText } from './sanitize-text';

describe('sanitizeDisplayText', () => {
  it('strips HTML tags and controls', () => {
    expect(sanitizeDisplayText('<script>alert(1)</script>Hello')).toBe('alert(1)Hello');
    expect(sanitizeDisplayText('a\u0000b\nc', { allowNewlines: false })).toBe('a b c');
  });

  it('respects maxLength and newlines', () => {
    expect(sanitizeDisplayText('abcdefghij', { maxLength: 5 })).toBe('abcde');
    expect(sanitizeDisplayText('a\n\n\nb', { allowNewlines: true })).toBe('a\n\nb');
  });
});

describe('encodeForHtml', () => {
  it('escapes HTML special characters after sanitize', () => {
    expect(encodeForHtml('<b>A&B</b>')).toBe('A&amp;B');
    expect(encodeForHtml('"quoted"')).toBe('&quot;quoted&quot;');
  });
});
