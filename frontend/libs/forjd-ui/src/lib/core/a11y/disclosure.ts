/**
 * Progressive disclosure store — smart defaults + remembered expand state (ADR-0022).
 * Dual-adapter: keep API aligned with viking-ui/core/disclosure.
 *
 * Advanced sections default collapsed so new users see essentials first.
 * Expand state persists in localStorage (never secrets).
 */

export const SUITE_DISCLOSURE_STORAGE_KEY = 'suite-disclosure-v1';

export type DisclosureStore = {
  readonly isOpen: (id: string, fallback?: boolean) => boolean;
  readonly setOpen: (id: string, open: boolean) => void;
  readonly toggle: (id: string, fallback?: boolean) => void;
  /** Clear one id (or all) so smart defaults apply again. */
  readonly reset: (id?: string) => void;
  /** Remembered expand map (suite data pack — ADR-0026). */
  readonly snapshot: () => Readonly<Record<string, boolean>>;
  /** Merge or replace remembered expand state (suite data pack — ADR-0026). */
  readonly importMap: (map: Readonly<Record<string, boolean>>, mode?: 'merge' | 'replace') => void;
  readonly subscribe: (listener: () => void) => () => void;
};

export type CreateDisclosureStoreOptions = {
  readonly storageKey?: string;
  /** Explicit defaults — missing ids fall back to `false` (collapsed). */
  readonly defaults?: Readonly<Record<string, boolean>>;
  readonly storage?: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null;
};

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

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

function readMap(storage: StorageLike | null, key: string): Record<string, boolean> {
  if (!storage) {
    return {};
  }
  try {
    const raw = storage.getItem(key);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {};
    }
    const out: Record<string, boolean> = {};
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (!id || typeof value !== 'boolean') {
        continue;
      }
      out[String(id).slice(0, 128)] = value;
    }
    return out;
  } catch {
    return {};
  }
}

function writeMap(storage: StorageLike | null, key: string, map: Record<string, boolean>): void {
  if (!storage) {
    return;
  }
  try {
    storage.setItem(key, JSON.stringify(map));
  } catch {
    // Quota / private mode — keep in-memory only.
  }
}

export function createDisclosureStore(options?: CreateDisclosureStoreOptions): DisclosureStore {
  const storageKey = options?.storageKey ?? SUITE_DISCLOSURE_STORAGE_KEY;
  const defaults = { ...(options?.defaults ?? {}) };
  const storage = safeStorage(options?.storage);
  let remembered = readMap(storage, storageKey);
  const listeners = new Set<() => void>();

  const notify = (): void => {
    for (const listener of listeners) {
      try {
        listener();
      } catch {
        // Listener failures must not break disclosure.
      }
    }
  };

  const resolve = (id: string, fallback?: boolean): boolean => {
    const key = String(id).slice(0, 128);
    if (!key) {
      return false;
    }
    if (Object.prototype.hasOwnProperty.call(remembered, key)) {
      return remembered[key]!;
    }
    if (fallback != null) {
      return fallback;
    }
    if (Object.prototype.hasOwnProperty.call(defaults, key)) {
      return defaults[key]!;
    }
    return false;
  };

  return {
    isOpen: (id, fallback) => resolve(id, fallback),
    setOpen: (id, open) => {
      const key = String(id).slice(0, 128);
      if (!key) {
        return;
      }
      if (remembered[key] === open) {
        return;
      }
      remembered = { ...remembered, [key]: open };
      writeMap(storage, storageKey, remembered);
      notify();
    },
    toggle: (id, fallback) => {
      const next = !resolve(id, fallback);
      const key = String(id).slice(0, 128);
      if (!key) {
        return;
      }
      remembered = { ...remembered, [key]: next };
      writeMap(storage, storageKey, remembered);
      notify();
    },
    reset: (id) => {
      if (id == null) {
        remembered = {};
        try {
          storage?.removeItem(storageKey);
        } catch {
          // ignore
        }
        notify();
        return;
      }
      const key = String(id).slice(0, 128);
      if (!key || !Object.prototype.hasOwnProperty.call(remembered, key)) {
        return;
      }
      const next = { ...remembered };
      delete next[key];
      remembered = next;
      writeMap(storage, storageKey, remembered);
      notify();
    },
    snapshot: () => ({ ...remembered }),
    importMap: (map, mode = 'merge') => {
      const incoming: Record<string, boolean> = {};
      for (const [id, value] of Object.entries(map)) {
        if (!id || typeof value !== 'boolean') {
          continue;
        }
        incoming[String(id).slice(0, 128)] = value;
      }
      remembered = mode === 'replace' ? incoming : { ...remembered, ...incoming };
      writeMap(storage, storageKey, remembered);
      notify();
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

let defaultStore: DisclosureStore | null = null;

/** Process-wide suite disclosure store (shared across disclosure hosts). */
export function getDefaultDisclosureStore(): DisclosureStore {
  return (defaultStore ??= createDisclosureStore());
}

/** Test helper — drop the singleton between suites. */
export function resetDefaultDisclosureStore(): void {
  defaultStore = null;
}
