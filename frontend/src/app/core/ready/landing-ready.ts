/**
 * Landing use-case: `/ready` probe + soft-failure breadcrumbs + SWR wiring.
 * Keeps presentation components free of fetch/monitoring details.
 * Pair with `createFetchHandle` + `settleReadyStatus` (ADR-0011 / ADR-0012).
 */

import { monitoringConfigFromEnvironment } from '../monitoring/monitoring.config';
import {
  READY_CACHE_POLICY,
  invalidateReadyProbe,
  markReadyProbeStale,
  probeApiReady,
  readyProbeAgeMs,
  subscribeReadyProbe,
  type ReadyProbeSettled,
  type ReadyProbeSoftFailure,
} from './ready-probe';

async function reportReadyBreadcrumb(
  outcome: ReadyProbeSoftFailure,
  data?: Record<string, unknown>,
): Promise<void> {
  // Offline is expected local state — do not spam trackers when the laptop sleeps.
  if (outcome === 'offline') {
    return;
  }
  const configuration = monitoringConfigFromEnvironment();
  if (!configuration) {
    return;
  }
  try {
    const { addMonitoringBreadcrumb } = await import('../monitoring/monitoring.facade');
    await addMonitoringBreadcrumb(
      {
        category: 'landing.ready',
        message: `FORJD /ready ${outcome}`,
        level: outcome === 'unreachable' ? 'warning' : 'info',
        data: { outcome, ...data },
      },
      configuration,
    );
  } catch {
    // Monitoring must not affect landing degradation UX.
  }
}

export async function probeLandingReady(apiBaseUrl: string): Promise<ReadyProbeSettled> {
  const readyUrl = `${apiBaseUrl.replace(/\/$/, '')}/ready`;
  return probeApiReady(readyUrl, {
    onSoftFailure: (outcome, data) => {
      void reportReadyBreadcrumb(outcome, data);
    },
  });
}

/** Hard invalidate before Retry — next probe blocks on network. */
export function retryLandingReady(): void {
  invalidateReadyProbe();
}

/**
 * Soft invalidate when the tab becomes visible again — next probe may SWR
 * without dropping the last painted status until the network returns.
 */
export function staleLandingReady(): void {
  markReadyProbeStale();
}

/**
 * Visibility re-check — skip while the probe is still fresh (spares mobile radio).
 * Returns true when the caller should soft-invalidate + silent probe.
 */
export function shouldRefreshLandingReadyOnVisible(now?: number): boolean {
  const age = readyProbeAgeMs(now);
  if (age === null) {
    return true;
  }
  return age >= READY_CACHE_POLICY.freshMs;
}

/** Background cache writes → landing `applySettled` without a loading flash. */
export function subscribeLandingReady(listener: (status: ReadyProbeSettled) => void): () => void {
  return subscribeReadyProbe(listener);
}

export type { ReadyProbeSettled, ReadyProbeStatus } from './ready-probe';
