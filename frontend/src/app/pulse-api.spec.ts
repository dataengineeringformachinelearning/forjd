import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { PulseApi } from './pulse-api';
import { SupabaseService } from './supabase';

describe('PulseApi', () => {
  let api: PulseApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        PulseApi,
        { provide: SupabaseService, useValue: { accessToken: () => Promise.resolve('jwt-test') } },
      ],
    });
    api = TestBed.inject(PulseApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('authenticates production pulse writes when a user session exists', async () => {
    const response = firstValueFrom(api.pulse([1, 2, 3]));
    await Promise.resolve();
    const request = http.expectOne((candidate) => candidate.url.endsWith('/api/v1/pulse'));
    expect(request.request.headers.get('Authorization')).toBe('Bearer jwt-test');
    expect(request.request.body).toEqual({ values: [1, 2, 3], source: 'angular-console' });
    request.flush({
      id: 'pulse-a',
      timestamp: 1,
      values: [1, 2, 3],
      ok: true,
      layers_ok: 1,
      layers_total: 1,
      layers: {},
    });
    await response;
  });

  it('authenticates the development-only anomaly control', async () => {
    const response = firstValueFrom(api.fitAnomaly());
    await Promise.resolve();
    const request = http.expectOne((candidate) => candidate.url.endsWith('/api/v1/anomaly/fit'));
    expect(request.request.headers.get('Authorization')).toBe('Bearer jwt-test');
    expect(request.request.body).toEqual({
      series_id: 'angular',
      use_synthetic: true,
      epochs: 20,
    });
    request.flush({ ok: true, model_version: 'test', series_id: 'angular' });
    await response;
  });
});
