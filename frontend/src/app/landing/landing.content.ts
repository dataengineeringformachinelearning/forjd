/**
 * Static product narrative + suite link builders for the public landing.
 * Flat structures only — no nested reactive state (ADR-0010).
 * External URLs are host-allowlisted (ADR-0013 open-redirect hygiene).
 */

import { safeHref, safeHttpBase } from 'forjd-ui';

export const LANDING_TITLE = 'FORJD' as const;

/** Hosts permitted for landing CTAs and API base (exact or subdomain). */
export const LANDING_LINK_HOSTS = [
  'forjd.co',
  'backend.forjd.co',
  'deml.app',
  'dataengineeringformachinelearning.com',
  'localhost',
  '127.0.0.1',
] as const;

const FALLBACK_API_BASE = 'https://backend.forjd.co';

export type LandingSuiteLinks = {
  readonly apiBaseUrl: string;
  readonly docsUrl: string;
  readonly redocUrl: string;
  readonly readyUrl: string;
  readonly privacyUrl: string;
  readonly termsUrl: string;
};

function suiteUrl(raw: string): string {
  return (
    safeHref(raw, { allowedHosts: LANDING_LINK_HOSTS }) ??
    safeHref(FALLBACK_API_BASE, { allowedHosts: LANDING_LINK_HOSTS }) ??
    FALLBACK_API_BASE
  );
}

export function landingSuiteLinks(apiBaseUrl: string): LandingSuiteLinks {
  const base =
    safeHttpBase(apiBaseUrl, {
      allowedHosts: LANDING_LINK_HOSTS,
      httpsOnlyExceptLoopback: true,
    }) ?? FALLBACK_API_BASE;
  return {
    apiBaseUrl: base,
    docsUrl: suiteUrl(`${base}/docs`),
    redocUrl: suiteUrl(`${base}/redoc`),
    readyUrl: suiteUrl(`${base}/ready`),
    privacyUrl: suiteUrl('https://dataengineeringformachinelearning.com/privacy/'),
    termsUrl: suiteUrl('https://dataengineeringformachinelearning.com/terms/'),
  };
}

/**
 * Control-plane readiness as one product story (loading → ready → soft failure).
 * Badge suffix + edge line + retry share this vocabulary — not ops jargon.
 */
export type LandingReadyError = 'offline' | 'unreachable' | 'not_ready';

export type LandingReadyStory = {
  readonly phase: 'loading' | 'ready' | 'degraded';
  readonly suffix: string | null;
  readonly detail: string | null;
  readonly tone: 'warning' | 'danger' | null;
  readonly retryLabel: string | null;
};

export function landingReadyStory(input: {
  readonly loading: boolean;
  readonly error: LandingReadyError | null;
}): LandingReadyStory {
  if (input.loading) {
    return {
      phase: 'loading',
      suffix: 'Confirming',
      detail: null,
      tone: null,
      retryLabel: null,
    };
  }
  if (input.error === null) {
    return {
      phase: 'ready',
      suffix: null,
      detail: null,
      tone: null,
      retryLabel: null,
    };
  }
  switch (input.error) {
    case 'offline':
      return {
        phase: 'degraded',
        suffix: 'Offline',
        detail: 'You are offline. This page stays available — reconnect to confirm sealed ingest.',
        tone: 'warning',
        retryLabel: 'Try again',
      };
    case 'unreachable':
      return {
        phase: 'degraded',
        suffix: 'Unavailable',
        detail:
          'FORJD could not be reached. Swagger and ReDoc still open — try again when the control plane answers.',
        tone: 'danger',
        retryLabel: 'Try again',
      };
    case 'not_ready':
      return {
        phase: 'degraded',
        suffix: 'Not ready',
        detail:
          'The control plane is not ready for sealed ingest yet. Docs stay available — try again shortly.',
        tone: 'warning',
        retryLabel: 'Try again',
      };
  }
}

/** Partner integrate sequence — Bind → Seal → Project → Operate. */
export const LANDING_STEPS = [
  {
    id: 'bind',
    step: '01',
    title: 'Bind',
    detail: 'Map a partner account to a FORJD tenant and mint a tenant-bound fjsvc_ token.',
  },
  {
    id: 'seal',
    step: '02',
    title: 'Seal',
    detail: 'Clients seal events end-to-end. The pipeline routes ciphertext only.',
  },
  {
    id: 'project',
    step: '03',
    title: 'Project',
    detail: 'Checkpoint durable stream_results, with replay and DLQ when delivery needs recovery.',
  },
  {
    id: 'operate',
    step: '04',
    title: 'Operate',
    detail: 'YAML workflows and rollups run under tenant RLS — one data plane.',
  },
] as const;
