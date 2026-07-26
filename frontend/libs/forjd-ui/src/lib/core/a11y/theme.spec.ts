import { describe, expect, it, beforeEach } from 'vitest';
import {
  applySuiteTheme,
  cycleSuiteThemePreference,
  prefersReducedMotion,
  readSuiteThemePreference,
  resolveSuiteTheme,
  writeSuiteThemePreference,
  SUITE_THEME_STORAGE_KEY,
} from './theme';

describe('forjd suite theme', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('defaults to system and resolves OS preference', () => {
    expect(readSuiteThemePreference(localStorage)).toBe('system');
    expect(resolveSuiteTheme('system', false)).toBe('light');
  });

  it('reads prefers-reduced-motion', () => {
    expect(prefersReducedMotion({ matches: true } as MediaQueryList)).toBe(true);
    expect(prefersReducedMotion({ matches: false } as MediaQueryList)).toBe(false);
    expect(prefersReducedMotion(null)).toBe(false);
  });

  it('persists and cycles', () => {
    writeSuiteThemePreference('light', localStorage);
    expect(localStorage.getItem(SUITE_THEME_STORAGE_KEY)).toBe('light');
    expect(cycleSuiteThemePreference('light')).toBe('dark');
    applySuiteTheme('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });
});
