import { createDisclosureStore, resetDefaultDisclosureStore } from './disclosure';

describe('createDisclosureStore', () => {
  afterEach(() => {
    resetDefaultDisclosureStore();
  });

  it('defaults advanced sections to collapsed', () => {
    const store = createDisclosureStore({ storage: null });
    expect(store.isOpen('deml.settings.telemetry')).toBe(false);
  });

  it('honors explicit defaults and remembers toggles', () => {
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
    const store = createDisclosureStore({
      storage,
      defaults: { 'demo.essentials': true },
    });
    expect(store.isOpen('demo.essentials')).toBe(true);
    expect(store.isOpen('demo.advanced')).toBe(false);

    store.toggle('demo.advanced');
    expect(store.isOpen('demo.advanced')).toBe(true);
    expect(memory.get('suite-disclosure-v1')).toContain('demo.advanced');

    store.reset('demo.advanced');
    expect(store.isOpen('demo.advanced')).toBe(false);
  });

  it('uses per-call fallback before global false', () => {
    const store = createDisclosureStore({ storage: null });
    expect(store.isOpen('x', true)).toBe(true);
    store.setOpen('x', false);
    expect(store.isOpen('x', true)).toBe(false);
  });

  it('snapshots and importMap merges or replaces', () => {
    const store = createDisclosureStore({ storage: null });
    store.setOpen('a', true);
    store.setOpen('b', false);
    expect(store.snapshot()).toEqual({ a: true, b: false });

    store.importMap({ c: true }, 'merge');
    expect(store.snapshot()).toEqual({ a: true, b: false, c: true });

    store.importMap({ d: true }, 'replace');
    expect(store.snapshot()).toEqual({ d: true });
    expect(store.isOpen('a')).toBe(false);
  });
});
