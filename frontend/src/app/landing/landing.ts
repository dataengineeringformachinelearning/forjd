import { Component, signal } from '@angular/core';

import { environment } from '../../environments/environment';

// --- Public product landing (static; no run controls) ---
@Component({
  selector: 'app-landing',
  templateUrl: './landing.html',
  styleUrl: './landing.scss',
})
export class Landing {
  protected readonly title = signal('FORJD');
  protected readonly apiBaseUrl = environment.apiBaseUrl;
  protected readonly docsUrl = `${environment.apiBaseUrl}/docs`;
  protected readonly redocUrl = `${environment.apiBaseUrl}/redoc`;

  protected readonly features = [
    { name: 'Sealed ingest', detail: 'X25519/HKDF + AES-256-GCM envelopes — ciphertext only.' },
    { name: 'Workflows', detail: 'YAML-configured pipelines orchestrated by Prefect.' },
    { name: 'Projections', detail: 'Checkpointed durable results with replay and DLQ.' },
    { name: 'Rust hot path', detail: 'Arrow/Parquet engine with a FastAPI control plane.' },
  ];
}
