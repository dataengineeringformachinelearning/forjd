import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { FjButton } from './button/button';
import { FjField } from './field/field';
import { FjSelect } from './select/select';
import { FjSwitch } from './switch/switch';

describe('forjd voice + switch access', () => {
  it('keeps field label usable for voice — no placeholder aria-label on select', async () => {
    @Component({
      imports: [FjField, FjSelect],
      template: `
        <forjd-field label="Status">
          <forjd-select placeholder="Choose…" [options]="[{ label: 'Open', value: 'open' }]" />
        </forjd-field>
      `,
    })
    class Host {}

    const fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
    await fixture.whenStable();

    const select = fixture.nativeElement.querySelector('select.suite-select') as HTMLSelectElement;
    expect(select.getAttribute('aria-label')).toBeNull();
    expect(fixture.nativeElement.querySelector('.suite-field-label')?.textContent).toContain(
      'Status',
    );
  });

  it('renders switch label input for accessible naming', async () => {
    @Component({
      imports: [FjSwitch],
      template: `<forjd-switch label="Enable alerts" />`,
    })
    class Host {}

    const fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.querySelector('.fj-switch-label')?.textContent).toContain(
      'Enable alerts',
    );
  });

  it('forwards aria-label on square buttons', async () => {
    @Component({
      imports: [FjButton],
      template: ` <forjd-button [square]="true" aria-label="Open menu">☰</forjd-button> `,
    })
    class Host {}

    const fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
    await fixture.whenStable();

    const btn = fixture.nativeElement.querySelector('button.suite-btn') as HTMLButtonElement;
    expect(btn.getAttribute('aria-label')).toBe('Open menu');
    expect(btn.getAttribute('data-square')).toBe('true');
  });
});
