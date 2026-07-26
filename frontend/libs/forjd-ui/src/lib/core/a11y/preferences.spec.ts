import {
  SUITE_PREFERENCES_STORAGE_KEY,
  createPreferencesStore,
  resetDefaultPreferencesStore,
} from './preferences';
import { SUITE_THEME_STORAGE_KEY } from './theme';

describe('createPreferencesStore', () => {
  afterEach(() => {
    resetDefaultPreferencesStore();
  });

  it('migrates suite-theme into the preferences blob', () => {
    const memory = new Map<string, string>();
    const storage = {
      getItem: (k: string) => memory.get(k) ?? null,
      setItem: (k: string, v: string) => {
        memory.set(k, v);
      },
      removeItem: (k: string) => {
        memory.delete(k);
      },
    };
    memory.set(SUITE_THEME_STORAGE_KEY, 'dark');
    const store = createPreferencesStore({ storage });
    expect(store.get().theme).toBe('dark');
    expect(memory.get(SUITE_PREFERENCES_STORAGE_KEY)).toContain('"dark"');
  });

  it('patches theme and mirrors suite-theme', () => {
    const memory = new Map<string, string>();
    const storage = {
      getItem: (k: string) => memory.get(k) ?? null,
      setItem: (k: string, v: string) => {
        memory.set(k, v);
      },
      removeItem: (k: string) => {
        memory.delete(k);
      },
    };
    const store = createPreferencesStore({ storage });
    store.patch({ theme: 'light' });
    expect(store.get().theme).toBe('light');
    expect(memory.get(SUITE_THEME_STORAGE_KEY)).toBe('light');
  });

  it('notifies subscribers on patch', () => {
    const store = createPreferencesStore({ storage: null });
    let ticks = 0;
    store.subscribe(() => {
      ticks += 1;
    });
    store.patch({ theme: 'dark' });
    expect(ticks).toBe(1);
  });
});
