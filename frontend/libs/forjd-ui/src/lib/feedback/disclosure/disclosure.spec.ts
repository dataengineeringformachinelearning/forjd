import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { resetDefaultDisclosureStore } from '../../core/a11y/disclosure';
import { FjDisclosure } from './disclosure';

describe('FjDisclosure', () => {
  beforeEach(async () => {
    resetDefaultDisclosureStore();
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [FjDisclosure],
    }).compileComponents();
  });

  afterEach(() => {
    resetDefaultDisclosureStore();
    localStorage.clear();
  });

  it('connects its trigger to the expanded region', () => {
    const fixture = TestBed.createComponent(FjDisclosure);
    fixture.componentRef.setInput('sectionId', 'test.disclosure');
    fixture.componentRef.setInput('heading', 'Advanced controls');
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    button.click();
    fixture.detectChanges();

    const panel = fixture.nativeElement.querySelector('[role="region"]') as HTMLElement;
    expect(button.getAttribute('aria-controls')).toBe(panel.id);
    expect(panel.getAttribute('aria-labelledby')).toBe(button.id);
    expect(button.getAttribute('aria-expanded')).toBe('true');
  });
});
