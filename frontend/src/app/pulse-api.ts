import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../environments/environment';

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

@Injectable({ providedIn: 'root' })
export class PulseApi {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  stack(): Observable<StackStatus> {
    return this.http.get<StackStatus>(`${this.base}/api/v1/stack`);
  }

  pulse(values?: number[]): Observable<PulseResult> {
    return this.http.post<PulseResult>(`${this.base}/api/v1/pulse`, {
      values: values ?? [1, 2, 3, 5, 8],
      source: 'angular',
    });
  }

  last(): Observable<PulseSnapshot> {
    return this.http.get<PulseSnapshot>(`${this.base}/api/v1/pulse`);
  }
}
