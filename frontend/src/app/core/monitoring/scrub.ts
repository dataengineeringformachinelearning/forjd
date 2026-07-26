/**
 * Strip secrets / ciphertext-looking fields before Sentry/Rollbar / console
 * payloads leave the browser. Keep patterns in lockstep with
 * `backend/app/core/sanitize.py` (`scrub_for_logs`).
 *
 * ADR: docs/adr/0005-observability-correlation-first.md
 * ADR: docs/adr/0017-secrets-and-sensitive-data.md
 */

const SENSITIVE_KEY_EXACT =
  /^(authorization|cookie|set[-_]?cookie|x[-_]?api[-_]?key|x[-_]?engine[-_]?token|password|secret|token|fjsvc_|ciphertext|sealed[_-]?payload|private[_-]?key|api[_-]?key|hibp[-_]?api[-_]?key|access[_-]?token|refresh[_-]?token|api[_-]?token|provision[_-]?token|engine[_-]?token|signing[_-]?secret|client[_-]?secret|jwt[_-]?secret|supabase[_-]?jwt[_-]?secret|dsn|sentry[_-]?dsn|rollbar[_-]?access[_-]?token|hf[_-]?token|postgres[_-]?dsn|redis[_-]?url|database[_-]?url|webhook[_-]?secret|object[_-]?storage[_-]?secret[_-]?access[_-]?key)$/i;

const SENSITIVE_KEY_SUFFIX =
  /(^|[_-])(password|secret|token|api[_-]?key|private[_-]?key|ciphertext|sealed[_-]?payload|access[_-]?token|refresh[_-]?token)$/i;

const SECRET_VALUE =
  /\b(fjsvc_[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._\-]+|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b|(?:postgres(?:ql)?|redis|rediss):\/\/[^\s"'<>]+/gi;

function isSecretKey(key: string): boolean {
  const normalized = key.trim();
  if (!normalized) {
    return false;
  }
  if (SENSITIVE_KEY_EXACT.test(normalized)) {
    return true;
  }
  return SENSITIVE_KEY_SUFFIX.test(normalized);
}

export function scrubString(value: string): string {
  return value.replace(SECRET_VALUE, '[Filtered]');
}

export function scrubValue(value: unknown, depth = 0): unknown {
  if (depth > 6) {
    return '[Truncated]';
  }
  if (typeof value === 'string') {
    return scrubString(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => scrubValue(item, depth + 1));
  }
  if (value instanceof Error) {
    return {
      name: scrubString(value.name),
      message: scrubString(value.message),
      stack: value.stack ? scrubString(value.stack) : undefined,
    };
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      if (isSecretKey(key)) {
        out[key] = '[Filtered]';
      } else {
        out[key] = scrubValue(nested, depth + 1);
      }
    }
    return out;
  }
  return value;
}

export type MonitoringBreadcrumb = {
  category: string;
  message: string;
  level?: 'info' | 'warning' | 'error';
  data?: Record<string, unknown>;
};

export function scrubBreadcrumb(breadcrumb: MonitoringBreadcrumb): MonitoringBreadcrumb {
  return {
    category: scrubString(breadcrumb.category),
    message: scrubString(breadcrumb.message),
    level: breadcrumb.level ?? 'info',
    data: breadcrumb.data ? (scrubValue(breadcrumb.data) as Record<string, unknown>) : undefined,
  };
}
