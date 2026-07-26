import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { recordSuiteActivity, resetDefaultActivityLog } from '../../core/a11y/activity-log';
import { resetDefaultDisclosureStore } from '../../core/a11y/disclosure';
import { resetDefaultOnboardingStore } from '../../core/a11y/onboarding';
import { resetDefaultPreferencesStore } from '../../core/a11y/preferences';
import { FjPreferencesService } from '../../chrome/preferences/preferences.service';
import { FjPreferencesPanel } from './preferences-panel';

describe('FjPreferencesPanel (integration)', () => {
  let fixture: ComponentFixture<FjPreferencesPanel>;
  let prefs: FjPreferencesService;

  beforeEach(async () => {
    resetDefaultPreferencesStore();
    resetDefaultDisclosureStore();
    resetDefaultOnboardingStore();
    resetDefaultActivityLog();

    await TestBed.configureTestingModule({
      imports: [FjPreferencesPanel],
    }).compileComponents();

    fixture = TestBed.createComponent(FjPreferencesPanel);
    prefs = TestBed.inject(FjPreferencesService);
    fixture.detectChanges();
  });

  afterEach(() => {
    TestBed.resetTestingModule();
    resetDefaultPreferencesStore();
    resetDefaultDisclosureStore();
    resetDefaultOnboardingStore();
    resetDefaultActivityLog();
  });

  it('renders theme, export/import, and activity sections', () => {
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Theme');
    expect(el.textContent).toContain('Export / import');
    expect(el.textContent).toContain('Recent activity');
    expect(el.textContent).toContain('No recent activity yet');
  });

  it('records activity when theme changes and lists it', () => {
    prefs.setTheme('dark');
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Theme set to dark');
    expect(el.querySelector('forjd-activity-list')).toBeTruthy();
  });

  it('shows clear activity after a recorded export action', () => {
    recordSuiteActivity({
      kind: 'preferences.export',
      label: 'Exported local preferences',
      source: 'forjd',
    });
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Exported local preferences');
    expect(el.textContent).toContain('Clear activity');
  });
});
