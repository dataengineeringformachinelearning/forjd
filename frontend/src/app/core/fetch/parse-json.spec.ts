import { describe, expect, it } from 'vitest';

import { parseResponseJson } from './parse-json';

describe('parseResponseJson', () => {
  it('returns ok value for JSON bodies', async () => {
    const response = new Response(JSON.stringify({ status: 'ready' }), {
      headers: { 'Content-Type': 'application/json' },
    });
    const parsed = await parseResponseJson(response);
    expect(parsed.ok).toBe(true);
    if (parsed.ok) {
      expect(parsed.value).toEqual({ status: 'ready' });
    }
  });

  it('returns soft failure for non-JSON bodies', async () => {
    const response = new Response('<html>nope</html>', {
      headers: { 'Content-Type': 'text/html' },
    });
    const parsed = await parseResponseJson(response);
    expect(parsed).toEqual({ ok: false, error: 'json' });
  });
});
