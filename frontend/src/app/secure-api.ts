import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, from, map, switchMap } from 'rxjs';

import { environment } from '../environments/environment';
import type { SealedEnvelope } from './crypto/seal';
import { SupabaseService } from './supabase';

export interface Tenant {
  id: string;
  slug: string;
  name: string;
  key_directory_id: string | null;
  created_at: string;
  role?: string;
}

export interface IngestResult {
  ok: boolean;
  accepted: number;
  new_events?: number;
  duplicates?: number;
  processing_state?: 'not_required' | 'completed' | 'failed';
  processing_mode?: 'synchronous';
  async_processing_available?: boolean;
  results: Array<{
    id: string;
    tenant_id: string;
    client_event_id: string;
    created_at: string;
    duplicate: boolean;
    workflow_id?: string | null;
  }>;
  prefect?: Record<string, unknown>;
}

@Injectable({ providedIn: 'root' })
export class SecureApi {
  private readonly http = inject(HttpClient);
  private readonly supabase = inject(SupabaseService);
  private readonly base = environment.apiBaseUrl;

  private withAuth(): Observable<HttpHeaders> {
    return from(this.supabase.accessToken()).pipe(
      map((token) => {
        if (!token) throw new Error('Sign in with Supabase Auth first');
        return new HttpHeaders({ Authorization: `Bearer ${token}` });
      }),
    );
  }

  listTenants(): Observable<{ ok: boolean; tenants: Tenant[] }> {
    return this.withAuth().pipe(
      switchMap((headers) =>
        this.http.get<{ ok: boolean; tenants: Tenant[] }>(`${this.base}/api/v1/tenants`, {
          headers,
        }),
      ),
    );
  }

  createTenant(slug: string, name: string): Observable<{ ok: boolean; tenant: Tenant }> {
    return this.withAuth().pipe(
      switchMap((headers) =>
        this.http.post<{ ok: boolean; tenant: Tenant }>(
          `${this.base}/api/v1/tenants`,
          { slug, name },
          { headers },
        ),
      ),
    );
  }

  /** Publish public X25519 material; private keys never enter this request. */
  upsertSession(opts: {
    tenantId: string;
    sessionId: string;
    identityPublicKey: string;
    ephemeralPublicKey?: string;
  }): Observable<Record<string, unknown>> {
    return this.withAuth().pipe(
      switchMap((headers) =>
        this.http.post<Record<string, unknown>>(
          `${this.base}/api/v1/sessions`,
          {
            tenant_id: opts.tenantId,
            session_id: opts.sessionId,
            identity_public_key: opts.identityPublicKey,
            ephemeral_public_key: opts.ephemeralPublicKey ?? null,
          },
          { headers },
        ),
      ),
    );
  }

  ingestSealed(opts: {
    tenantId: string;
    clientEventId: string;
    envelope: SealedEnvelope;
    metadata?: Record<string, unknown>;
  }): Observable<IngestResult> {
    const body = {
      tenant_id: opts.tenantId,
      client_event_id: opts.clientEventId,
      envelope: {
        algo: opts.envelope.algo,
        key_id: opts.envelope.keyId,
        nonce: opts.envelope.nonce,
        ciphertext: opts.envelope.ciphertext,
        ratchet_header: opts.envelope.ratchetHeader,
        ciphertext_sha256: opts.envelope.ciphertextSha256,
      },
      metadata: opts.metadata ?? { source: 'angular' },
    };
    return this.withAuth().pipe(
      switchMap((headers) =>
        this.http.post<IngestResult>(`${this.base}/api/v1/ingest`, body, { headers }),
      ),
    );
  }
}
