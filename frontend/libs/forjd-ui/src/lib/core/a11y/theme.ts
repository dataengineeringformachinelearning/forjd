/**
 * Suite theme helpers (forjd-ui adapter — keep API aligned with viking-ui/core/theme).
 */

export type SuiteThemePreference = 'light' | 'dark' | 'system';
export type SuiteThemeResolved = 'light' | 'dark';

export const SUITE_THEME_STORAGE_KEY = 'suite-theme';
const LEGACY_THEME_STORAGE_KEY = 'theme';
export const SUITE_THEME_CHANGE_EVENT = 'suite-theme-change';

export function prefersDarkScheme(
  media: MediaQueryList | null | undefined = typeof window !== 'undefined'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null,
): boolean {
  return media?.matches ?? true;
}

/** WCAG 2.3.3 — true when the user asks for reduced motion. */
export function prefersReducedMotion(
  media: MediaQueryList | null | undefined = typeof window !== 'undefined'
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : null,
): boolean {
  return media?.matches ?? false;
}

export function resolveSuiteTheme(
  preference: SuiteThemePreference,
  systemPrefersDark: boolean = prefersDarkScheme(),
): SuiteThemeResolved {
  if (preference === 'system') {
    return systemPrefersDark ? 'dark' : 'light';
  }
  return preference;
}

/** Accessible name for the suite theme toggle (voice / SR). */
export function suiteThemeToggleAriaLabel(
  preference: SuiteThemePreference,
  resolved: SuiteThemeResolved,
): string {
  if (preference === 'system') {
    return resolved === 'dark'
      ? 'Theme: system (dark). Switch to light'
      : 'Theme: system (light). Switch to dark';
  }
  return resolved === 'dark' ? 'Theme: dark. Switch to light' : 'Theme: light. Switch to dark';
}

export function parseSuiteThemePreference(
  value: string | null | undefined,
): SuiteThemePreference | null {
  if (value === 'light' || value === 'dark' || value === 'system') {
    return value;
  }
  return null;
}

export function readSuiteThemePreference(
  storage: Pick<Storage, 'getItem'> | null | undefined = typeof localStorage !== 'undefined'
    ? localStorage
    : null,
): SuiteThemePreference {
  if (!storage) return 'system';
  const modern = parseSuiteThemePreference(storage.getItem(SUITE_THEME_STORAGE_KEY));
  if (modern) return modern;
  const legacy = parseSuiteThemePreference(storage.getItem(LEGACY_THEME_STORAGE_KEY));
  if (legacy === 'light' || legacy === 'dark') return legacy;
  return 'system';
}

export function writeSuiteThemePreference(
  preference: SuiteThemePreference,
  storage: Pick<Storage, 'setItem' | 'removeItem'> | null | undefined = typeof localStorage !==
  'undefined'
    ? localStorage
    : null,
): void {
  if (!storage) return;
  storage.setItem(SUITE_THEME_STORAGE_KEY, preference);
  if (preference === 'system') {
    storage.removeItem(LEGACY_THEME_STORAGE_KEY);
  } else {
    storage.setItem(LEGACY_THEME_STORAGE_KEY, preference);
  }
}

/** Apply resolved theme to the document. Returns true when DOM actually changed. */
export function applySuiteTheme(
  resolved: SuiteThemeResolved,
  root: HTMLElement | null = typeof document !== 'undefined' ? document.documentElement : null,
): boolean {
  if (!root) return false;
  const already =
    root.getAttribute('data-theme') === resolved &&
    root.style.colorScheme === resolved &&
    root.classList.contains('dark') === (resolved === 'dark');
  if (already) return false;
  root.setAttribute('data-theme', resolved);
  root.classList.toggle('dark', resolved === 'dark');
  root.style.colorScheme = resolved;
  return true;
}

export function dispatchSuiteThemeChange(detail: {
  preference: SuiteThemePreference;
  resolved: SuiteThemeResolved;
}): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(SUITE_THEME_CHANGE_EVENT, { bubbles: true, detail }));
}

export function toggleSuiteThemePreference(
  preference: SuiteThemePreference,
  systemPrefersDark: boolean = prefersDarkScheme(),
): SuiteThemePreference {
  const resolved = resolveSuiteTheme(preference, systemPrefersDark);
  return resolved === 'dark' ? 'light' : 'dark';
}

export function cycleSuiteThemePreference(preference: SuiteThemePreference): SuiteThemePreference {
  switch (preference) {
    case 'system':
      return 'light';
    case 'light':
      return 'dark';
    case 'dark':
      return 'system';
  }
}
