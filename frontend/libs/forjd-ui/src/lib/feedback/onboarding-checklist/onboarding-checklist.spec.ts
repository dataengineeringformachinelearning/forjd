import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { getDefaultActivityLog, resetDefaultActivityLog } from '../../core/a11y/activity-log';
import { getDefaultOnboardingStore, resetDefaultOnboardingStore } from '../../core/a11y/onboarding';
import { FjOnboardingChecklist } from './onboarding-checklist';

@Component({
  imports: [FjOnboardingChecklist],
  template: `
    <forjd-onboarding-checklist
      flowId="forjd-partner"
      heading="Partner deploy"
      [steps]="steps"
      [autoHide]="false"
    />
  `,
})
class Host {
  readonly steps = [
    { id: 'bind', title: 'Bind', description: 'Map tenant' },
    { id: 'seal', title: 'Seal', description: 'Encrypt events' },
  ];
}

describe('FjOnboardingChecklist (integration)', () => {
  let fixture: ComponentFixture<Host>;

  beforeEach(async () => {
    resetDefaultOnboardingStore();
    resetDefaultActivityLog();
    await TestBed.configureTestingModule({
      imports: [Host],
    }).compileComponents();
    fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
  });

  afterEach(() => {
    TestBed.resetTestingModule();
    resetDefaultOnboardingStore();
    resetDefaultActivityLog();
  });

  it('renders steps and completes a checked step', () => {
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Partner deploy');
    expect(el.textContent).toContain('Bind');
    const checkbox = el.querySelector('input.suite-onboarding-check') as HTMLInputElement;
    expect(checkbox).toBeTruthy();
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(getDefaultOnboardingStore().isStepComplete('bind')).toBe(true);
  });

  it('records activity when dismissed', () => {
    const el = fixture.nativeElement as HTMLElement;
    const buttons = [...el.querySelectorAll('forjd-button button')];
    const dismiss = buttons.find((b) => (b.textContent ?? '').includes('Dismiss')) as
      HTMLButtonElement | undefined;
    expect(dismiss).toBeTruthy();
    dismiss!.click();
    fixture.detectChanges();
    expect(getDefaultOnboardingStore().get().dismissed).toBe(true);
    expect(
      getDefaultActivityLog()
        .list()
        .some((e) => e.kind === 'onboarding.dismiss'),
    ).toBe(true);
  });
});
