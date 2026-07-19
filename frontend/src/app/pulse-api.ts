import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, from, map, switchMap } from 'rxjs';

import { environment } from '../environments/environment';
import { SupabaseService } from './supabase';

export interface StackStatus {
  ok: boolean;
  environment: string;
  checks: Record<string, { ok: boolean; [key: string]: unknown }>;
}

export interface PulseResult {
  id: string;
  timestamp: number;
  values: number[];
  ok: boolean;
  layers_ok: number;
  layers_total: number;
  layers: Record<string, { ok?: boolean; [key: string]: unknown }>;
}

export interface PulseSnapshot {
  engine: { ok: boolean; mode?: string; version?: string; error?: string; [key: string]: unknown };
  cached: Record<string, unknown> | null;
  recent: Array<Record<string, unknown>>;
}

export interface AnomalyFitResult {
  ok: boolean;
  model_version: string;
  series_id: string;
  layers?: Record<string, { ok?: boolean; [key: string]: unknown }>;
  error?: string;
}

export interface AnomalyScoreResult {
  ok: boolean;
  model_version: string;
  series_id: string;
  reconstruction_error: number;
  threshold: number;
  is_anomaly: boolean;
  embedding: number[];
  embedding_id: string | null;
  neighbors: Array<{
    id: string;
    series_id: string;
    reconstruction_error: number;
    is_anomaly: boolean;
    distance: number;
  }>;
  layers?: Record<string, { ok?: boolean; [key: string]: unknown }>;
  error?: string;
}

@Injectable({ providedIn: 'root' })
export class PulseApi {
  private readonly http = inject(HttpClient);
  private readonly supabase = inject(SupabaseService);
  private readonly base = environment.apiBaseUrl;

  stack(): Observable<StackStatus> {
    return this.http.get<StackStatus>(`${this.base}/api/v1/stack`);
  }

  pulse(values?: number[]): Observable<PulseResult> {
    return this.authHeaders(false).pipe(
      switchMap((headers) =>
        this.http.post<PulseResult>(
          `${this.base}/api/v1/pulse`,
          { values: values ?? [1, 2, 3, 5, 8], source: 'angular-console' },
          { headers },
        ),
      ),
    );
  }

  last(): Observable<PulseSnapshot> {
    return this.http.get<PulseSnapshot>(`${this.base}/api/v1/pulse`);
  }

  fitAnomaly(): Observable<AnomalyFitResult> {
    return this.authHeaders(true).pipe(
      switchMap((headers) =>
        this.http.post<AnomalyFitResult>(
          `${this.base}/api/v1/anomaly/fit`,
          { series_id: 'angular', use_synthetic: true, epochs: 20 },
          { headers },
        ),
      ),
    );
  }

  scoreAnomaly(values?: number[]): Observable<AnomalyScoreResult> {
    return this.authHeaders(true).pipe(
      switchMap((headers) =>
        this.http.post<AnomalyScoreResult>(
          `${this.base}/api/v1/anomaly/score`,
          {
            values: values ?? [0.1, 0.2, 8, 9, 0.1, 0.2, 0.1, 0.2, 0.1, 0.2, 0.1, 0.2],
            series_id: 'angular',
            persist: true,
            neighbors: 3,
          },
          { headers },
        ),
      ),
    );
  }

  private authHeaders(required: boolean): Observable<HttpHeaders> {
    return from(this.supabase.accessToken()).pipe(
      map((token) => {
        if (!token && required) throw new Error('Sign in before using anomaly controls');
        return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
      }),
    );
  }
}
