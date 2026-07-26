/**
 * Plain-text sanitizer + HTML encoding for UGC / third-party strings.
 * Dual-adapter: keep API aligned with viking-ui/core/sanitize-text.
 * Prefer Angular `{{ }}` (auto-escapes). Use `encodeForHtml` only for
 * rare HTML-attribute / string-template sinks — never `[innerHTML]`.
 *
 * ADR: docs/adr/0014-sanitize-ugc-and-third-party.md
 * ADR: docs/adr/0015-rate-limit-validation-output-encoding.md
 */

export type SanitizeTextOptions = {
  readonly maxLength?: number;
  readonly allowNewlines?: boolean;
};

const TAG_RE = /<[^>]*>/g;
const CONTROL_RE = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g;

/** Strip markup/controls from a display string (never trust third-party HTML). */
export function sanitizeDisplayText(
  raw: string | null | undefined,
  options: SanitizeTextOptions = {},
): string {
  if (raw == null) {
    return '';
  }
  let text = String(raw);
  text = text.replace(TAG_RE, '');
  if (options.allowNewlines) {
    text = text.replace(/\r\n?/g, '\n').replace(CONTROL_RE, ' ');
    text = text.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n');
    text = text.replace(/[^\S\n]+/g, ' ');
  } else {
    text = text.replace(/[\r\n\t]+/g, ' ').replace(CONTROL_RE, ' ');
    text = text.replace(/\s+/g, ' ');
  }
  text = text.trim();
  const max = options.maxLength;
  if (max != null && max >= 0 && text.length > max) {
    text = text.slice(0, max).trimEnd();
  }
  return text;
}

/** Sanitize then HTML-escape for attribute / template-literal sinks. */
export function encodeForHtml(
  raw: string | null | undefined,
  options: SanitizeTextOptions = {},
): string {
  return sanitizeDisplayText(raw, options)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
