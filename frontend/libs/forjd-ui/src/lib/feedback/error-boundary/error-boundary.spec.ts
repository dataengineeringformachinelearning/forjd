import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { FjErrorBoundary } from './error-boundary';

describe('FjErrorBoundary', () => {
  it('shows projected content when healthy', async () => {
    @Component({
      imports: [FjErrorBoundary],
      template: `
        <forjd-error-boundary>
          <p id="ok">healthy</p>
        </forjd-error-boundary>
      `,
    })
    class Host {}

    await TestBed.configureTestingModule({ imports: [Host] }).compileComponents();
    const fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('#ok')?.textContent).toContain('healthy');
    expect(fixture.nativeElement.querySelector('forjd-error-state')).toBeNull();
  });

  it('swaps to error state when failed and recovers on retry', async () => {
    @Component({
      imports: [FjErrorBoundary],
      template: `
        <forjd-error-boundary [(failed)]="failed" title="Broken section">
          <p id="ok">healthy</p>
        </forjd-error-boundary>
      `,
    })
    class Host {
      failed = true;
    }

    await TestBed.configureTestingModule({ imports: [Host] }).compileComponents();
    const fixture = TestBed.createComponent(Host);
    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    expect(host.querySelector('#ok')).toBeNull();
    expect(host.querySelector('.suite-error-state-title')?.textContent).toContain('Broken section');

    host.querySelector('button')?.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.failed).toBe(false);
    expect(host.querySelector('#ok')?.textContent).toContain('healthy');
  });
});
