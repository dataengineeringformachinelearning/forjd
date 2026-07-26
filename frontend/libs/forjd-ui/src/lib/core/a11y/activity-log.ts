/**
 * Suite activity log — important soft-chrome actions (ADR-0027).
 * Dual-adapter: keep API aligned with viking-ui/core/activity-log.
 *
 * Local, capped, metadata-only. Never secrets, tokens, or ciphertext.
 * Not a substitute for server `audit_events` / DEML AuditLog.
 */

export const SUITE_ACTIVITY_STORAGE_KEY = 'suite-activity-v1';
export const SUITE_ACTIVITY_CHANGE_EVENT = 'suite-activity-change';

const DEFAULT_MAX_ENTRIES = 50;
const KIND_MAX = 64;
const LABEL_MAX = 200;
const DETAIL_MAX = 200;

const SENSITIVE = /fjsvc_|Bearer\s|eyJ[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{10,}|api[_-]?key\s*[:=]/i;

export type SuiteActivitySource = 'forjd' | 'deml' | 'suite';

export type SuiteActivityEntry = {
  readonly id: string;
  readonly at: number;
  readonly kind: string;
  readonly label: string;
  readonly detail?: string;
  readonly source?: SuiteActivitySource;
};

export type ActivityLogRecordInput = {
  readonly kind: string;
  readonly label: string;
  readonly detail?: string;
  readonly source?: SuiteActivitySource;
  readonly at?: number;
};

export type ActivityLog = {
  readonly list: () => readonly SuiteActivityEntry[];
  readonly record: (input: ActivityLogRecordInput) => SuiteActivityEntry | null;
  readonly clear: () => void;
  readonly subscribe: (listener: () => void) => () => void;
  readonly bindSync: (options?: { readonly target?: Window }) => () => void;
};

export type CreateActivityLogOptions = {
  readonly storageKey?: string;
  readonly maxEntries?: number;
  readonly storage?: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null;
};

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

type ActivityBlob = {
  readonly version: 1;
  readonly entries: readonly SuiteActivityEntry[];
  readonly updatedAt: number;
};

function safeStorage(explicit?: StorageLike | null): StorageLike | null {
  if (explicit !== undefined) {
    return explicit;
  }
  try {
    if (typeof globalThis.localStorage === 'undefined') {
      return null;
    }
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

function scrubText(value: string, max: number): string | null {
  const text = value.trim().replace(/\s+/g, ' ').slice(0, max);
  if (!text || SENSITIVE.test(text)) {
    return null;
  }
  return text;
}

function sanitizeSource(value: unknown): SuiteActivitySource | undefined {
  if (value === 'forjd' || value === 'deml' || value === 'suite') {
    return value;
  }
  return undefined;
}

function sanitizeEntry(raw: unknown): SuiteActivityEntry | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return null;
  }
  const row = raw as Record<string, unknown>;
  const kind = scrubText(String(row['kind'] ?? ''), KIND_MAX);
  const label = scrubText(String(row['label'] ?? ''), LABEL_MAX);
  if (!kind || !label) {
    return null;
  }
  const detailRaw = row['detail'];
  const detail =
    typeof detailRaw === 'string' ? (scrubText(detailRaw, DETAIL_MAX) ?? undefined) : undefined;
  const at = Number(row['at']);
  const id = String(row['id'] ?? '').slice(0, 64) || `act-${at || Date.now()}`;
  return {
    id,
    at: Number.isFinite(at) ? at : Date.now(),
    kind,
    label,
    detail: detail || undefined,
    source: sanitizeSource(row['source']),
  };
}

function readBlob(storage: StorageLike | null, key: string): ActivityBlob {
  if (!storage) {
    return { version: 1, entries: [], updatedAt: 0 };
  }
  try {
    const raw = storage.getItem(key);
    if (!raw) {
      return { version: 1, entries: [], updatedAt: 0 };
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { version: 1, entries: [], updatedAt: 0 };
    }
    const row = parsed as Record<string, unknown>;
    const entriesRaw = row['entries'];
    const entries = Array.isArray(entriesRaw)
      ? entriesRaw.map(sanitizeEntry).filter((e): e is SuiteActivityEntry => e != null)
      : [];
    const updatedAt = Number(row['updatedAt']);
    return {
      version: 1,
      entries,
      updatedAt: Number.isFinite(updatedAt) ? updatedAt : 0,
    };
  } catch {
    return { version: 1, entries: [], updatedAt: 0 };
  }
}

function writeBlob(storage: StorageLike | null, key: string, blob: ActivityBlob): void {
  if (!storage) {
    return;
  }
  try {
    storage.setItem(key, JSON.stringify(blob));
  } catch {
    // Quota / private mode — keep in-memory only.
  }
}

function dispatchChange(blob: ActivityBlob): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(
    new CustomEvent(SUITE_ACTIVITY_CHANGE_EVENT, {
      bubbles: true,
      detail: blob,
    }),
  );
}

let activitySeq = 0;

export function createActivityLog(options?: CreateActivityLogOptions): ActivityLog {
  const storageKey = options?.storageKey ?? SUITE_ACTIVITY_STORAGE_KEY;
  const maxEntries = Math.max(1, options?.maxEntries ?? DEFAULT_MAX_ENTRIES);
  const storage = safeStorage(options?.storage);
  let blob = readBlob(storage, storageKey);
  if (blob.entries.length > maxEntries) {
    blob = {
      ...blob,
      entries: blob.entries.slice(0, maxEntries),
      updatedAt: Date.now(),
    };
    writeBlob(storage, storageKey, blob);
  }

  const listeners = new Set<() => void>();

  const notify = (): void => {
    for (const listener of listeners) {
      try {
        listener();
      } catch {
        // Listener failures must not break activity.
      }
    }
  };

  const commit = (next: ActivityBlob, source: 'local' | 'sync' = 'local'): void => {
    blob = next;
    if (source !== 'sync') {
      writeBlob(storage, storageKey, blob);
      dispatchChange(blob);
    }
    notify();
  };

  return {
    list: () => blob.entries,
    record: (input) => {
      const kind = scrubText(String(input.kind ?? ''), KIND_MAX);
      const label = scrubText(String(input.label ?? ''), LABEL_MAX);
      if (!kind || !label) {
        return null;
      }
      const detail = input.detail ? (scrubText(input.detail, DETAIL_MAX) ?? undefined) : undefined;
      const at = input.at ?? Date.now();
      activitySeq += 1;
      const entry: SuiteActivityEntry = {
        id: `act-${at}-${activitySeq}`,
        at,
        kind,
        label,
        detail: detail || undefined,
        source: sanitizeSource(input.source),
      };
      const entries = [entry, ...blob.entries].slice(0, maxEntries);
      commit({ version: 1, entries, updatedAt: Date.now() });
      return entry;
    },
    clear: () => {
      commit({ version: 1, entries: [], updatedAt: Date.now() });
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    bindSync: (bindOpts) => {
      const win = bindOpts?.target ?? (typeof window !== 'undefined' ? window : null);
      if (!win) {
        return () => undefined;
      }
      const onStorage = (event: StorageEvent): void => {
        if (event.key !== storageKey) {
          return;
        }
        const remote = readBlob(storage, storageKey);
        if (remote.updatedAt < blob.updatedAt) {
          return;
        }
        commit(remote, 'sync');
      };
      const onCustom = (event: Event): void => {
        const detail = (event as CustomEvent<ActivityBlob>).detail;
        if (!detail || typeof detail !== 'object') {
          return;
        }
        if (Number(detail.updatedAt) <= blob.updatedAt) {
          return;
        }
        const entries = Array.isArray(detail.entries)
          ? detail.entries
              .map(sanitizeEntry)
              .filter((e): e is SuiteActivityEntry => e != null)
              .slice(0, maxEntries)
          : [];
        commit(
          {
            version: 1,
            entries,
            updatedAt: Number(detail.updatedAt) || Date.now(),
          },
          'sync',
        );
      };
      win.addEventListener('storage', onStorage);
      win.addEventListener(SUITE_ACTIVITY_CHANGE_EVENT, onCustom);
      return () => {
        win.removeEventListener('storage', onStorage);
        win.removeEventListener(SUITE_ACTIVITY_CHANGE_EVENT, onCustom);
      };
    },
  };
}

let defaultLog: ActivityLog | null = null;

export function getDefaultActivityLog(): ActivityLog {
  return (defaultLog ??= createActivityLog());
}

export function resetDefaultActivityLog(): void {
  defaultLog = null;
}

/** Convenience for adapters — records against the process default log. */
export function recordSuiteActivity(input: ActivityLogRecordInput): SuiteActivityEntry | null {
  return getDefaultActivityLog().record(input);
}
