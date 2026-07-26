/**
 * Suite preferences store — persist + cross-tab sync (ADR-0024).
 * Dual-adapter: keep API aligned with viking-ui/core/preferences.
 *
 * Soft UI chrome only (theme, …). Never store secrets, tokens, or auth.
 * Theme also mirrors `suite-theme` for FOUC / legacy readers.
 */

import {
  type SuiteThemePreference,
  parseSuiteThemePreference,
  readSuiteThemePreference,
  writeSuiteThemePreference,
  SUITE_THEME_STORAGE_KEY,
} from './theme';

export const SUITE_PREFERENCES_STORAGE_KEY = 'suite-preferences-v1';
export const SUITE_PREFERENCES_CHANGE_EVENT = 'suite-preferences-change';

export type SuitePreferences = {
  readonly theme: SuiteThemePreference;
  /** Epoch ms — last-write-wins across tabs. */
  readonly updatedAt: number;
};

export type PreferencesPatch = {
  readonly theme?: SuiteThemePreference;
};

export type PreferencesStore = {
  readonly get: () => SuitePreferences;
  readonly patch: (
    partial: PreferencesPatch,
    opts?: { readonly source?: 'local' | 'theme' | 'sync' },
  ) => SuitePreferences;
  readonly reset: () => SuitePreferences;
  readonly subscribe: (listener: () => void) => () => void;
  /** Listen for `storage` + same-tab CustomEvent. */
  readonly bindSync: (options?: { readonly target?: Window }) => () => void;
};

export type CreatePreferencesStoreOptions = {
  readonly storageKey?: string;
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

function defaults(): SuitePreferences {
  return {
    theme: 'system',
    updatedAt: 0,
  };
}

function sanitize(raw: unknown, fallbackTheme: SuiteThemePreference): SuitePreferences {
  const base = defaults();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { ...base, theme: fallbackTheme, updatedAt: Date.now() };
  }
  const row = raw as Record<string, unknown>;
  const theme =
    parseSuiteThemePreference(typeof row['theme'] === 'string' ? row['theme'] : null) ??
    fallbackTheme;
  const updatedAt = Number(row['updatedAt']);
  return {
    theme,
    updatedAt: Number.isFinite(updatedAt) ? updatedAt : Date.now(),
  };
}

function readBlob(storage: StorageLike | null, key: string): SuitePreferences | null {
  if (!storage) {
    return null;
  }
  try {
    const raw = storage.getItem(key);
    if (!raw) {
      return null;
    }
    return sanitize(JSON.parse(raw) as unknown, readSuiteThemePreference(storage));
  } catch {
    return null;
  }
}

function writeBlob(storage: StorageLike | null, key: string, prefs: SuitePreferences): void {
  if (!storage) {
    return;
  }
  try {
    storage.setItem(key, JSON.stringify(prefs));
  } catch {
    // Quota / private mode — keep in-memory only.
  }
}

function dispatchChange(prefs: SuitePreferences): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(
    new CustomEvent(SUITE_PREFERENCES_CHANGE_EVENT, {
      bubbles: true,
      detail: prefs,
    }),
  );
}

export function createPreferencesStore(options?: CreatePreferencesStoreOptions): PreferencesStore {
  const storageKey = options?.storageKey ?? SUITE_PREFERENCES_STORAGE_KEY;
  const storage = safeStorage(options?.storage);
  const migratedTheme = readSuiteThemePreference(storage);
  let state: SuitePreferences =
    readBlob(storage, storageKey) ??
    ({
      theme: migratedTheme,
      updatedAt: Date.now(),
    } satisfies SuitePreferences);

  // Ensure blob exists after migrate so other tabs can sync.
  if (!readBlob(storage, storageKey)) {
    writeBlob(storage, storageKey, state);
  }

  const listeners = new Set<() => void>();

  const notify = (): void => {
    for (const listener of listeners) {
      try {
        listener();
      } catch {
        // Listener failures must not break preferences.
      }
    }
  };

  const applyLocal = (
    next: SuitePreferences,
    source: 'local' | 'theme' | 'sync',
  ): SuitePreferences => {
    state = next;
    if (source !== 'sync') {
      writeBlob(storage, storageKey, state);
      if (source !== 'theme') {
        writeSuiteThemePreference(state.theme, storage);
      }
      dispatchChange(state);
    }
    notify();
    return state;
  };

  return {
    get: () => state,
    patch: (partial, opts) => {
      const source = opts?.source ?? 'local';
      const theme = partial.theme ?? state.theme;
      if (theme === state.theme && source === 'local' && partial.theme != null) {
        return state;
      }
      if (theme === state.theme && source === 'theme') {
        // Still mirror into the blob when theme service persists.
        return applyLocal({ theme, updatedAt: Date.now() }, 'theme');
      }
      if (theme === state.theme && source === 'sync') {
        return state;
      }
      return applyLocal({ theme, updatedAt: Date.now() }, source);
    },
    reset: () => applyLocal({ theme: 'system', updatedAt: Date.now() }, 'local'),
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
        if (event.storageArea && storage && event.storageArea !== storage) {
          return;
        }
        if (event.key !== storageKey && event.key !== SUITE_THEME_STORAGE_KEY) {
          return;
        }
        const remote =
          readBlob(storage, storageKey) ??
          ({
            theme: readSuiteThemePreference(storage),
            updatedAt: Date.now(),
          } satisfies SuitePreferences);
        if (remote.theme === state.theme && remote.updatedAt === state.updatedAt) {
          return;
        }
        // Last-write-wins by updatedAt when both blobs exist.
        if (remote.updatedAt < state.updatedAt && event.key === storageKey) {
          return;
        }
        applyLocal(remote, 'sync');
      };

      const onCustom = (event: Event): void => {
        const detail = (event as CustomEvent<SuitePreferences>).detail;
        if (!detail || typeof detail !== 'object') {
          return;
        }
        const remote = sanitize(detail, state.theme);
        if (remote.theme === state.theme) {
          return;
        }
        applyLocal(remote, 'sync');
      };

      win.addEventListener('storage', onStorage);
      win.addEventListener(SUITE_PREFERENCES_CHANGE_EVENT, onCustom);
      return () => {
        win.removeEventListener('storage', onStorage);
        win.removeEventListener(SUITE_PREFERENCES_CHANGE_EVENT, onCustom);
      };
    },
  };
}

let defaultStore: PreferencesStore | null = null;

export function getDefaultPreferencesStore(): PreferencesStore {
  return (defaultStore ??= createPreferencesStore());
}

export function resetDefaultPreferencesStore(): void {
  defaultStore = null;
}
