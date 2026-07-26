import { applySuiteDataPack, exportSuiteDataPack, parseSuiteDataPack } from './suite-data-pack';
import { getDefaultPreferencesStore, resetDefaultPreferencesStore } from './preferences';
import { getDefaultDisclosureStore, resetDefaultDisclosureStore } from './disclosure';
import { getDefaultOnboardingStore, resetDefaultOnboardingStore } from './onboarding';

describe('suite data pack', () => {
  afterEach(() => {
    resetDefaultPreferencesStore();
    resetDefaultDisclosureStore();
    resetDefaultOnboardingStore();
  });

  it('parses a valid pack and rejects secrets fields', () => {
    const ok = parseSuiteDataPack({
      kind: 'suite-data-pack',
      version: 1,
      exportedAt: 1,
      preferences: { theme: 'dark', updatedAt: 1 },
    });
    expect(ok.ok).toBe(true);

    const bad = parseSuiteDataPack({
      kind: 'suite-data-pack',
      version: 1,
      exportedAt: 1,
      api_token: 'fjsvc_nope',
    });
    expect(bad.ok).toBe(false);

    const jwt = parseSuiteDataPack({
      kind: 'suite-data-pack',
      version: 1,
      exportedAt: 1,
      bearer: 'eyJhbGciOiJIUzI1NiJ9.payload.sig',
    });
    expect(jwt.ok).toBe(false);
  });

  it('rejects unknown kind', () => {
    const bad = parseSuiteDataPack({
      kind: 'not-a-pack',
      version: 1,
      exportedAt: 1,
    });
    expect(bad.ok).toBe(false);
  });

  it('applies preferences, disclosure, and onboarding (merge)', () => {
    getDefaultDisclosureStore().setOpen('keep.me', true);
    const pack = {
      kind: 'suite-data-pack' as const,
      version: 1 as const,
      exportedAt: Date.now(),
      preferences: { theme: 'light' as const, updatedAt: Date.now() },
      disclosure: { 'demo.section': true },
      onboarding: {
        version: 1 as const,
        dismissed: false,
        completed: false,
        completedSteps: ['bind'],
        activeFlow: 'forjd-partner' as const,
        updatedAt: Date.now(),
      },
    };
    const parsed = parseSuiteDataPack(pack);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) {
      return;
    }
    const result = applySuiteDataPack(parsed.pack, { mode: 'merge' });
    expect(result.applied).toEqual(['preferences', 'disclosure', 'onboarding']);
    expect(getDefaultPreferencesStore().get().theme).toBe('light');
    expect(getDefaultDisclosureStore().isOpen('keep.me')).toBe(true);
    expect(getDefaultDisclosureStore().isOpen('demo.section')).toBe(true);
    expect(getDefaultOnboardingStore().isStepComplete('bind')).toBe(true);
  });

  it('replace mode overwrites disclosure map', () => {
    getDefaultDisclosureStore().setOpen('old.section', true);
    const parsed = parseSuiteDataPack({
      kind: 'suite-data-pack',
      version: 1,
      exportedAt: Date.now(),
      disclosure: { 'new.section': true },
    });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) {
      return;
    }
    applySuiteDataPack(parsed.pack, { mode: 'replace' });
    expect(getDefaultDisclosureStore().snapshot()).toEqual({
      'new.section': true,
    });
  });

  it('builds an export object with kind suite-data-pack', () => {
    const pack = exportSuiteDataPack();
    expect(pack.kind).toBe('suite-data-pack');
    expect(pack.version).toBe(1);
    expect(pack.preferences).toBeTruthy();
    expect(pack.recentSearches).toBeUndefined();
  });

  it('round-trips export → parse → apply', () => {
    getDefaultPreferencesStore().patch({ theme: 'dark' });
    getDefaultOnboardingStore().completeStep('operate');
    const exported = exportSuiteDataPack();
    resetDefaultPreferencesStore();
    resetDefaultOnboardingStore();
    const parsed = parseSuiteDataPack(exported);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) {
      return;
    }
    applySuiteDataPack(parsed.pack, { mode: 'replace' });
    expect(getDefaultPreferencesStore().get().theme).toBe('dark');
    expect(getDefaultOnboardingStore().isStepComplete('operate')).toBe(true);
  });
});
