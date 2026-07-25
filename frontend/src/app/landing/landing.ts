import { ChangeDetectionStrategy, Component } from '@angular/core';
import {
  FjButton,
  FjPageShell,
  FjPanel,
  FjSection,
  FjSeparator,
} from 'forjd-ui';

import { environment } from '../../environments/environment';

// --- Public product landing (composition only — suite-landing.css owns look) ---
@Component({
  selector: 'app-landing',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton, FjPageShell, FjPanel, FjSection, FjSeparator],
  templateUrl: './landing.html',
})
export class Landing {
  protected readonly title = 'FORJD';
  protected readonly apiBaseUrl = environment.apiBaseUrl;
  protected readonly docsUrl = `${environment.apiBaseUrl}/docs`;
  protected readonly redocUrl = `${environment.apiBaseUrl}/redoc`;
  protected readonly communityUrl = 'https://dataengineeringformachinelearning.com/';

  protected readonly onboarding = [
    {
      step: '01',
      title: 'Bind',
      detail: 'Map a partner account to a FORJD tenant and mint a tenant-bound fjsvc_ token.',
    },
    {
      step: '02',
      title: 'Seal',
      detail: 'Clients seal events with X25519/HKDF + AES-256-GCM. The pipeline never sees plaintext.',
    },
    {
      step: '03',
      title: 'Project',
      detail: 'Checkpoint durable stream_results with replay and DLQ when delivery needs recovery.',
    },
    {
      step: '04',
      title: 'Operate',
      detail: 'YAML workflows, rollups, and ML refresh run under tenant RLS — no parallel data plane.',
    },
  ] as const;

  protected readonly capabilityBands = [
    {
      tag: 'INGEST',
      title: 'Sealed intake at the edge',
      detail:
        'Partner apps keep their own end-user auth. FORJD accepts only tenant-bound service tokens and sealed envelopes — never Firebase or partner end-user JWTs.',
      panelTitle: 'Envelope path',
      metrics: [
        { label: 'Content', value: 'Ciphertext only' },
        { label: 'Keys', value: 'X25519 / HKDF' },
        { label: 'Storage', value: 'AES-256-GCM' },
      ],
    },
    {
      tag: 'WORKFLOWS',
      title: 'Configurable sealed pipelines',
      detail:
        'YAML under backend/workflows drives Prefect orchestration with a Rust sealed hot path and a dependency-free Python soft fallback.',
      panelTitle: 'Execution',
      metrics: [
        { label: 'Hot path', value: 'Rust / Arrow' },
        { label: 'Orchestration', value: 'Prefect 3' },
        { label: 'Batch tables', value: 'Polars' },
      ],
    },
    {
      tag: 'PROJECTIONS',
      title: 'Durable results with replay',
      detail:
        'Checkpointed stream_results, replay, and DLQ keep operational history intact across tenants without leaking cross-tenant state.',
      panelTitle: 'Durability',
      metrics: [
        { label: 'Results', value: 'Checkpointed' },
        { label: 'Recovery', value: 'Replay / DLQ' },
        { label: 'Isolation', value: 'Postgres RLS' },
      ],
    },
  ] as const;

  protected readonly pillars = [
    {
      name: 'Ciphertext lane',
      detail: 'E2EE sealed ingest — the pipeline routes ciphertext only.',
    },
    {
      name: 'Tenant binding',
      detail: 'fjsvc_ tokens and body/query tenant IDs must match or fail closed.',
    },
    {
      name: 'RLS isolation',
      detail: 'Postgres row-level security on every tenant-scoped read and write.',
    },
    {
      name: 'Partner boundary',
      detail: 'Subprocessors keep end-user auth; FORJD never accepts partner user tokens.',
    },
  ] as const;

  protected readonly features = [
    { name: 'Sealed ingest', detail: 'X25519/HKDF + AES-256-GCM envelopes — ciphertext only.' },
    { name: 'Workflows', detail: 'YAML-configured pipelines orchestrated by Prefect.' },
    { name: 'Projections', detail: 'Checkpointed durable results with replay and DLQ.' },
    { name: 'Rust hot path', detail: 'Arrow/Parquet engine with a FastAPI control plane.' },
  ] as const;
}
