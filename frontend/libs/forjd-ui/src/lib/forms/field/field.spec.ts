import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { FjInput } from '../input/input';
import { FjField } from './field';

describe('forjd-field', () => {
  it('associates messages and marks the control invalid', async () => {
    @Component({
      imports: [FjField, FjInput],
      template: `
        <forjd-field label="Email" description="Work email" error="Required" [required]="true">
          <forjd-input type="email" />
        </forjd-field>
      `,
    })
    class Host {}

    const fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
    await fixture.whenStable();

    const desc = fixture.nativeElement.querySelector('.suite-field-description') as HTMLElement;
    const err = fixture.nativeElement.querySelector('.suite-field-error') as HTMLElement;
    const input = fixture.nativeElement.querySelector('input.suite-input') as HTMLInputElement;

    expect(err.getAttribute('role')).toBe('alert');
    expect(err.getAttribute('aria-live')).toBe('assertive');
    expect(err.textContent).toContain('Error:');
    expect(desc.textContent).toContain('Work email');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(input.getAttribute('aria-describedby')?.split(/\s+/)).toEqual(
      expect.arrayContaining([desc.id, err.id]),
    );
  });
});
