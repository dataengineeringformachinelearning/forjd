/**
 * Suite onboarding progress — first-time guidance (ADR-0025).
 * Dual-adapter: keep API aligned with viking-ui/core/onboarding.
 *
 * Journey state only (dismiss / complete / step ids). Never secrets or tokens.
 * Separate from suite-preferences-v1 (ADR-0024 soft chrome).
 */

export const SUITE_ONBOARDING_STORAGE_KEY = 'suite-onboarding-v1';
export const SUITE_ONBOARDING_CHANGE_EVENT = 'suite-onboarding-change';

/** Legacy DEML keys — migrated once into the suite blob. */
const LEGACY_SKIP_KEY = 'deml_onboarding_skipped';
const LEGACY_COMPLETE_KEY = 'deml_onboarding_complete';

export type SuiteOnboardingFlow = 'deml-status' | 'forjd-partner' | null;

export type SuiteOnboardingState = {
  readonly version: 1;
  readonly dismissed: boolean;
  readonly completed: boolean;
  readonly completedSteps: readonly string[];
  readonly activeFlow: SuiteOnboardingFlow;
  readonly updatedAt: number;
};

export type OnboardingStore = {
  readonly get: () => SuiteOnboardingState;
  readonly shouldShowGuide: () => boolean;
  readonly isStepComplete: (id: string) => boolean;
  readonly completeStep: (id: string) => void;
  readonly incompleteStep: (id: string) => void;
  readonly markComplete: () => void;
  readonly markDismissed: () => void;
  readonly setActiveFlow: (flow: SuiteOnboardingFlow) => void;
  readonly reset: () => void;
  /** Merge or replace journey state (suite data pack — ADR-0026). */
  readonly importState: (raw: unknown, mode?: 'merge' | 'replace') => void;
  readonly subscribe: (listener: () => void) => () => void;
  readonly bindSync: (options?: { readonly target?: Window }) => () => void;
};

export type CreateOnboardingStoreOptions = {
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

function defaults(): SuiteOnboardingState {
  return {
    version: 1,
    dismissed: false,
    completed: false,
    completedSteps: [],
    activeFlow: null,
    updatedAt: 0,
  };
}

function sanitizeFlow(value: unknown): SuiteOnboardingFlow {
  if (value === 'deml-status' || value === 'forjd-partner') {
    return value;
  }
  return null;
}

function sanitize(raw: unknown): SuiteOnboardingState {
  const base = defaults();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { ...base, updatedAt: Date.now() };
  }
  const row = raw as Record<string, unknown>;
  const stepsRaw = row['completedSteps'];
  const completedSteps = Array.isArray(stepsRaw)
    ? stepsRaw
        .map((s) => String(s).slice(0, 64))
        .filter(Boolean)
        .slice(0, 32)
    : [];
  const updatedAt = Number(row['updatedAt']);
  return {
    version: 1,
    dismissed: row['dismissed'] === true,
    completed: row['completed'] === true,
    completedSteps,
    activeFlow: sanitizeFlow(row['activeFlow']),
    updatedAt: Number.isFinite(updatedAt) ? updatedAt : Date.now(),
  };
}

function migrateLegacy(storage: StorageLike | null): SuiteOnboardingState | null {
  if (!storage) {
    return null;
  }
  try {
    const complete = storage.getItem(LEGACY_COMPLETE_KEY) === 'true';
    const skipped = storage.getItem(LEGACY_SKIP_KEY) === 'true';
    if (!complete && !skipped) {
      return null;
    }
    return {
      version: 1,
      dismissed: skipped && !complete,
      completed: complete,
      completedSteps: complete ? ['welcome', 'site', 'endpoint', 'publish', 'done'] : [],
      activeFlow: 'deml-status',
      updatedAt: Date.now(),
    };
  } catch {
    return null;
  }
}

function clearLegacy(storage: StorageLike | null): void {
  if (!storage) {
    return;
  }
  try {
    storage.removeItem(LEGACY_SKIP_KEY);
    storage.removeItem(LEGACY_COMPLETE_KEY);
  } catch {
    // ignore
  }
}

function readBlob(storage: StorageLike | null, key: string): SuiteOnboardingState | null {
  if (!storage) {
    return null;
  }
  try {
    const raw = storage.getItem(key);
    if (!raw) {
      return null;
    }
    return sanitize(JSON.parse(raw) as unknown);
  } catch {
    return null;
  }
}

function writeBlob(storage: StorageLike | null, key: string, state: SuiteOnboardingState): void {
  if (!storage) {
    return;
  }
  try {
    storage.setItem(key, JSON.stringify(state));
  } catch {
    // Quota / private mode — keep in-memory only.
  }
}

function dispatchChange(state: SuiteOnboardingState): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(
    new CustomEvent(SUITE_ONBOARDING_CHANGE_EVENT, {
      bubbles: true,
      detail: state,
    }),
  );
}

export function createOnboardingStore(options?: CreateOnboardingStoreOptions): OnboardingStore {
  const storageKey = options?.storageKey ?? SUITE_ONBOARDING_STORAGE_KEY;
  const storage = safeStorage(options?.storage);
  let fromLegacy = false;
  const existing = readBlob(storage, storageKey);
  let state: SuiteOnboardingState =
    existing ??
    (() => {
      const migrated = migrateLegacy(storage);
      if (migrated) {
        fromLegacy = true;
        return migrated;
      }
      return { ...defaults(), updatedAt: Date.now() };
    })();

  if (fromLegacy || !existing) {
    writeBlob(storage, storageKey, state);
    if (fromLegacy) {
      clearLegacy(storage);
    }
  }

  const listeners = new Set<() => void>();

  const notify = (): void => {
    for (const listener of listeners) {
      try {
        listener();
      } catch {
        // Listener failures must not break onboarding.
      }
    }
  };

  const commit = (next: SuiteOnboardingState, source: 'local' | 'sync' = 'local'): void => {
    state = next;
    if (source !== 'sync') {
      writeBlob(storage, storageKey, state);
      dispatchChange(state);
    }
    notify();
  };

  return {
    get: () => state,
    shouldShowGuide: () => !state.completed && !state.dismissed,
    isStepComplete: (id) => state.completedSteps.includes(String(id)),
    completeStep: (id) => {
      const key = String(id).slice(0, 64);
      if (!key || state.completedSteps.includes(key)) {
        return;
      }
      commit({
        ...state,
        completedSteps: [...state.completedSteps, key],
        updatedAt: Date.now(),
      });
    },
    incompleteStep: (id) => {
      const key = String(id);
      if (!state.completedSteps.includes(key)) {
        return;
      }
      commit({
        ...state,
        completedSteps: state.completedSteps.filter((s) => s !== key),
        completed: false,
        updatedAt: Date.now(),
      });
    },
    markComplete: () => {
      commit({
        ...state,
        completed: true,
        dismissed: false,
        updatedAt: Date.now(),
      });
    },
    markDismissed: () => {
      commit({
        ...state,
        dismissed: true,
        updatedAt: Date.now(),
      });
    },
    setActiveFlow: (flow) => {
      if (flow === state.activeFlow) {
        return;
      }
      commit({
        ...state,
        activeFlow: flow,
        updatedAt: Date.now(),
      });
    },
    reset: () => {
      commit({ ...defaults(), updatedAt: Date.now() });
      clearLegacy(storage);
    },
    importState: (raw, mode = 'merge') => {
      const incoming = sanitize(raw);
      if (mode === 'replace') {
        commit({ ...incoming, updatedAt: Date.now() });
        return;
      }
      const steps = Array.from(
        new Set([...state.completedSteps, ...incoming.completedSteps]),
      ).slice(0, 32);
      commit({
        version: 1,
        dismissed: state.dismissed || incoming.dismissed,
        completed: state.completed || incoming.completed,
        completedSteps: steps,
        activeFlow: incoming.activeFlow ?? state.activeFlow,
        updatedAt: Date.now(),
      });
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
        if (!remote || remote.updatedAt < state.updatedAt) {
          return;
        }
        commit(remote, 'sync');
      };
      const onCustom = (event: Event): void => {
        const detail = (event as CustomEvent<SuiteOnboardingState>).detail;
        if (!detail || typeof detail !== 'object') {
          return;
        }
        const remote = sanitize(detail);
        if (remote.updatedAt <= state.updatedAt) {
          return;
        }
        commit(remote, 'sync');
      };
      win.addEventListener('storage', onStorage);
      win.addEventListener(SUITE_ONBOARDING_CHANGE_EVENT, onCustom);
      return () => {
        win.removeEventListener('storage', onStorage);
        win.removeEventListener(SUITE_ONBOARDING_CHANGE_EVENT, onCustom);
      };
    },
  };
}

let defaultStore: OnboardingStore | null = null;

export function getDefaultOnboardingStore(): OnboardingStore {
  return (defaultStore ??= createOnboardingStore());
}

export function resetDefaultOnboardingStore(): void {
  defaultStore = null;
}

/** Standard empty-state eyebrow for first-time guidance surfaces. */
export const SUITE_EMPTY_GUIDANCE_EYEBROW = 'Getting started';
