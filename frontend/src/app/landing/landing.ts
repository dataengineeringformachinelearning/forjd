import { Component, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { environment } from '../../environments/environment';

// --- Public product landing ---
@Component({
  selector: 'app-landing',
  imports: [RouterLink],
  templateUrl: './landing.html',
  styleUrl: './landing.scss',
})
export class Landing {
  protected readonly title = signal('FORJD');
  protected readonly apiBaseUrl = environment.apiBaseUrl;
  protected readonly docsUrl = `${environment.apiBaseUrl}/docs`;
  protected readonly redocUrl = `${environment.apiBaseUrl}/redoc`;
  protected readonly healthUrl = `${environment.apiBaseUrl}/health`;

  protected readonly features = [
    { name: 'Sealed ingest', detail: 'X25519/HKDF + AES-256-GCM envelopes — ciphertext only.' },
    { name: 'Workflows', detail: 'YAML-configured pipelines orchestrated by Prefect.' },
    { name: 'Projections', detail: 'Checkpointed durable results with replay and DLQ.' },
    { name: 'Analytics', detail: 'Tenant-scoped rollups, status pages, and exports.' },
    { name: 'Machine learning', detail: 'Anomaly scoring and embeddings over stream metadata.' },
    { name: 'Rust hot path', detail: 'Arrow/Parquet engine with a FastAPI control plane.' },
  ];
}
