import { describe, expect, it } from 'vitest';

import { suiteThemeToggleAriaLabel } from './theme';

describe('suiteThemeToggleAriaLabel', () => {
  it('names system and explicit preferences', () => {
    expect(suiteThemeToggleAriaLabel('system', 'dark')).toBe(
      'Theme: system (dark). Switch to light',
    );
    expect(suiteThemeToggleAriaLabel('light', 'light')).toBe('Theme: light. Switch to dark');
  });
});
