/**
 * Safe JSON parse for Response bodies — unexpected shapes / non-JSON
 * become soft failures instead of uncaught SyntaxError.
 *
 * ADR: docs/adr/0018-defensive-outbound-http.md
 */

export type ParseJsonResult =
  { readonly ok: true; readonly value: unknown } | { readonly ok: false; readonly error: 'json' };

/** Parse `response.json()` without throwing on malformed bodies. */
export async function parseResponseJson(response: Response): Promise<ParseJsonResult> {
  try {
    const value: unknown = await response.json();
    return { ok: true, value };
  } catch {
    return { ok: false, error: 'json' };
  }
}
