import {
  SUITE_ONBOARDING_STORAGE_KEY,
  createOnboardingStore,
  resetDefaultOnboardingStore,
} from './onboarding';

describe('createOnboardingStore', () => {
  afterEach(() => {
    resetDefaultOnboardingStore();
  });

  function memoryStorage(seed?: Record<string, string>) {
    const memory = new Map<string, string>(Object.entries(seed ?? {}));
    return {
      getItem: (k: string) => memory.get(k) ?? null,
      setItem: (k: string, v: string) => {
        memory.set(k, v);
      },
      removeItem: (k: string) => {
        memory.delete(k);
      },
      memory,
    };
  }

  it('migrates legacy deml onboarding complete flags', () => {
    const storage = memoryStorage({
      deml_onboarding_complete: 'true',
    });
    const store = createOnboardingStore({ storage });
    expect(store.get().completed).toBe(true);
    expect(store.shouldShowGuide()).toBe(false);
    expect(storage.memory.get(SUITE_ONBOARDING_STORAGE_KEY)).toContain('"completed":true');
    expect(storage.memory.get('deml_onboarding_complete')).toBeUndefined();
  });

  it('migrates legacy skipped as dismissed', () => {
    const storage = memoryStorage({
      deml_onboarding_skipped: 'true',
    });
    const store = createOnboardingStore({ storage });
    expect(store.get().dismissed).toBe(true);
    expect(store.shouldShowGuide()).toBe(false);
  });

  it('tracks steps and marks complete when requested', () => {
    const store = createOnboardingStore({ storage: null });
    expect(store.shouldShowGuide()).toBe(true);
    store.completeStep('bind');
    expect(store.isStepComplete('bind')).toBe(true);
    store.markComplete();
    expect(store.shouldShowGuide()).toBe(false);
  });

  it('notifies subscribers on dismiss', () => {
    const store = createOnboardingStore({ storage: null });
    let ticks = 0;
    store.subscribe(() => {
      ticks += 1;
    });
    store.markDismissed();
    expect(ticks).toBe(1);
    expect(store.get().dismissed).toBe(true);
  });

  it('importState merges steps and replace overwrites', () => {
    const store = createOnboardingStore({ storage: null });
    store.completeStep('welcome');
    store.importState(
      {
        version: 1,
        dismissed: false,
        completed: false,
        completedSteps: ['site'],
        activeFlow: 'deml-status',
        updatedAt: Date.now(),
      },
      'merge',
    );
    expect(store.isStepComplete('welcome')).toBe(true);
    expect(store.isStepComplete('site')).toBe(true);
    expect(store.get().activeFlow).toBe('deml-status');

    store.importState(
      {
        version: 1,
        dismissed: true,
        completed: false,
        completedSteps: ['bind'],
        activeFlow: 'forjd-partner',
        updatedAt: Date.now(),
      },
      'replace',
    );
    expect(store.isStepComplete('welcome')).toBe(false);
    expect(store.isStepComplete('bind')).toBe(true);
    expect(store.get().dismissed).toBe(true);
    expect(store.get().activeFlow).toBe('forjd-partner');
  });
});
