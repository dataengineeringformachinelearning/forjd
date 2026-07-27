/**
 * High-level landing critical-path integration (sequence + ready probe shell).
 * Complements Playwright e2e for CI without a live browser when e2e is skipped.
 */
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Landing } from './landing';

describe('Landing critical paths (integration)', () => {
  beforeEach(async () => {
    vi.stubGlobal('navigator', { onLine: true });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ status: 'ok' }, { status: 200 })),
    );
    await TestBed.configureTestingModule({
      imports: [Landing],
    }).compileComponents();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('keeps a thin partner surface: hero CTAs + integrate sequence only', async () => {
    const fixture = TestBed.createComponent(Landing);
    fixture.detectChanges();
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('forjd-onboarding-checklist')).toBeNull();
    expect(el.querySelector('forjd-search-palette')).toBeNull();
    expect(el.querySelector('forjd-preferences')).toBeNull();
    expect(el.querySelector('.landing__capabilities')).toBeNull();
    expect(el.textContent).toContain('How partners integrate');
    const integrationCards = [...el.querySelectorAll<HTMLElement>('forjd-panel.landing__feature')];
    expect(integrationCards).toHaveLength(4);
    expect(integrationCards.every((card) => !card.hasAttribute('role'))).toBe(true);
    expect(
      el.querySelectorAll('[aria-label="Primary"] forjd-button, [aria-label="Primary"] a').length,
    ).toBeGreaterThanOrEqual(2);
    const labelledSections = [...el.querySelectorAll('forjd-section[aria-labelledby]')];
    expect(labelledSections).toHaveLength(2);
    for (const section of labelledSections) {
      expect(section.getAttribute('role')).toBe('region');
      expect(el.querySelector(`#${section.getAttribute('aria-labelledby')}`)).not.toBeNull();
    }
  });
});
