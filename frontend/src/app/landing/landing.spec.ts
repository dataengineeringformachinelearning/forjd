import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { invalidateReadyProbe } from '../core/ready/ready-probe';
import { Landing } from './landing';

describe('Landing', () => {
  beforeEach(async () => {
    invalidateReadyProbe();
    await TestBed.configureTestingModule({
      imports: [Landing],
    }).compileComponents();
  });

  afterEach(() => {
    invalidateReadyProbe();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('keeps the public product page at the root experience', async () => {
    const fixture = TestBed.createComponent(Landing);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.fj-brand')?.textContent).toContain('FORJD');
    expect(element.querySelectorAll('forjd-panel.landing__feature').length).toBe(4);
    expect(element.querySelectorAll('.landing__band').length).toBe(0);
    expect(element.querySelector('forjd-search-palette')).toBeNull();
  });

  it('links to API documentation and legal — no runnable console', async () => {
    const fixture = TestBed.createComponent(Landing);
    await fixture.whenStable();
    const links = [...(fixture.nativeElement as HTMLElement).querySelectorAll('a')];
    expect(links.some((link) => link.getAttribute('href') === '/console')).toBe(false);
    expect(links.some((link) => link.getAttribute('href')?.endsWith('/docs'))).toBe(true);
    expect(links.some((link) => link.getAttribute('href')?.endsWith('/redoc'))).toBe(true);
    expect(
      links.some((link) =>
        link.getAttribute('href')?.includes('dataengineeringformachinelearning.com'),
      ),
    ).toBe(true);
  });

  it('keeps the primary narrative clear and folds unreachable into the badge (20%)', async () => {
    vi.stubGlobal('navigator', { onLine: true });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch');
      }),
    );

    const fixture = TestBed.createComponent(Landing);
    fixture.detectChanges();
    await fixture.whenStable();
    // afterNextRender + probe
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const badge = element.querySelector('.suite-landing-badge') as HTMLElement | null;
    expect(badge?.getAttribute('data-phase')).toBe('degraded');
    expect(badge?.getAttribute('data-tone')).toBe('danger');
    expect(badge?.textContent).toContain('Unavailable');
    expect(element.querySelector('.suite-landing-badge-retry')?.textContent).toMatch(/Try again/);
    expect(element.querySelector('.landing__ready-edge')?.textContent).toMatch(/control plane/i);
    // No interrupting callout section between hero and sequence.
    expect(element.querySelector('.landing__api-degraded')).toBeNull();
    expect(element.querySelector('.fj-brand')?.textContent).toContain('FORJD');
    expect(element.textContent).toContain('How partners integrate');
  });

  it('shows offline on the badge without treating the API as down', async () => {
    vi.stubGlobal('navigator', { onLine: false });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const fixture = TestBed.createComponent(Landing);
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const badge = element.querySelector('.suite-landing-badge') as HTMLElement | null;
    expect(badge?.getAttribute('data-phase')).toBe('degraded');
    expect(badge?.getAttribute('data-tone')).toBe('warning');
    expect(badge?.textContent).toContain('Offline');
    expect(element.textContent).not.toContain('Unavailable');
    expect(element.querySelector('.landing__ready-edge')?.textContent).toMatch(/sealed ingest/i);
    expect(element.querySelector('.landing__api-degraded')).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(element.querySelector('.fj-brand')?.textContent).toContain('FORJD');
  });

  it('settles the happy path to a quiet ready chapter', async () => {
    vi.stubGlobal('navigator', { onLine: true });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ status: 'ready' }, { status: 200 })),
    );

    const fixture = TestBed.createComponent(Landing);
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const badge = element.querySelector('.suite-landing-badge') as HTMLElement | null;
    expect(badge?.getAttribute('data-phase')).toBe('ready');
    expect(badge?.getAttribute('data-tone')).toBeNull();
    expect(badge?.textContent).toMatch(/Production/);
    expect(badge?.textContent).not.toMatch(/Confirming|Live|Offline|Unavailable/);
    expect(element.querySelector('.landing__ready-edge')).toBeNull();
    expect(element.querySelector('.suite-landing-badge-retry')).toBeNull();
  });
});
