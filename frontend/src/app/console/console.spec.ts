import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { BehaviorSubject, of } from 'rxjs';

import { PulseApi } from '../pulse-api';
import { SecureApi } from '../secure-api';
import { SupabaseService } from '../supabase';
import { Console } from './console';

describe('Console', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Console],
      providers: [
        provideRouter([]),
        {
          provide: PulseApi,
          useValue: {
            stack: () => of({ ok: true, environment: 'test', checks: { api: { ok: true } } }),
          },
        },
        {
          provide: SecureApi,
          useValue: { listTenants: () => of({ ok: true, tenants: [] }) },
        },
        {
          provide: SupabaseService,
          useValue: {
            configured: false,
            session$: new BehaviorSubject(null),
            subscribeTelemetry: () => () => undefined,
          },
        },
      ],
    }).compileComponents();
  });

  it('restores stack, pulse, anomaly, and E2EE controls under the console', async () => {
    const fixture = TestBed.createComponent(Console);
    fixture.detectChanges();
    await fixture.whenStable();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Secure streaming operations');
    expect(text).toContain('Run pulse');
    expect(text).toContain('Fit + score dev anomaly');
    expect(text).toContain('Secure stream (E2EE)');
  });

  it('does not request or render credentials when browser auth is unconfigured', async () => {
    const fixture = TestBed.createComponent(Console);
    fixture.detectChanges();
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('input[type="password"]')).toBeNull();
    expect(element.textContent).toContain('Never place a service-role key');
  });
});
