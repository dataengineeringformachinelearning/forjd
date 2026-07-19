import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { SecureApi } from './secure-api';
import { SupabaseService } from './supabase';

describe('SecureApi', () => {
  let api: SecureApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        SecureApi,
        { provide: SupabaseService, useValue: { accessToken: () => Promise.resolve('jwt-test') } },
      ],
    });
    api = TestBed.inject(SecureApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('uses the user bearer token without placing it in the request body', async () => {
    const response = firstValueFrom(api.listTenants());
    await Promise.resolve();
    const request = http.expectOne((candidate) => candidate.url.endsWith('/api/v1/tenants'));
    expect(request.request.headers.get('Authorization')).toBe('Bearer jwt-test');
    expect(request.request.body).toBeNull();
    request.flush({ ok: true, tenants: [] });
    await expect(response).resolves.toEqual({ ok: true, tenants: [] });
  });

  it('maps only a sealed envelope and routing metadata onto ingest', async () => {
    const response = firstValueFrom(
      api.ingestSealed({
        tenantId: 'tenant-a',
        clientEventId: 'event-a',
        envelope: {
          algo: 'aes-256-gcm',
          keyId: 'browser-a',
          nonce: 'bm9uY2U=',
          ciphertext: 'Y2lwaGVydGV4dA==',
          ratchetHeader: null,
          ciphertextSha256: 'a'.repeat(64),
        },
        metadata: { source: 'angular-console' },
      }),
    );
    await Promise.resolve();
    const request = http.expectOne((candidate) => candidate.url.endsWith('/api/v1/ingest'));
    expect(request.request.headers.get('Authorization')).toBe('Bearer jwt-test');
    expect(request.request.body).toEqual({
      tenant_id: 'tenant-a',
      client_event_id: 'event-a',
      envelope: {
        algo: 'aes-256-gcm',
        key_id: 'browser-a',
        nonce: 'bm9uY2U=',
        ciphertext: 'Y2lwaGVydGV4dA==',
        ratchet_header: null,
        ciphertext_sha256: 'a'.repeat(64),
      },
      metadata: { source: 'angular-console' },
    });
    expect(JSON.stringify(request.request.body)).not.toContain('jwt-test');
    request.flush({ ok: true, accepted: 1, results: [] });
    await response;
  });

  it('publishes only X25519 public material for a browser session', async () => {
    const response = firstValueFrom(
      api.upsertSession({
        tenantId: 'tenant-a',
        sessionId: 'browser-a',
        identityPublicKey: 'identity-public',
        ephemeralPublicKey: 'ephemeral-public',
      }),
    );
    await Promise.resolve();
    const request = http.expectOne((candidate) => candidate.url.endsWith('/api/v1/sessions'));
    expect(request.request.body).toEqual({
      tenant_id: 'tenant-a',
      session_id: 'browser-a',
      identity_public_key: 'identity-public',
      ephemeral_public_key: 'ephemeral-public',
    });
    expect(JSON.stringify(request.request.body)).not.toContain('private');
    request.flush({ ok: true });
    await response;
  });
});
