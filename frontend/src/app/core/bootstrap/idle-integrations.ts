/**
 * Idle-deferred third-party integrations — keep bootstrap free of SDK details.
 * Defer when offline (ADR-0009); skip when Save-Data / prefers-reduced-data.
 */

import { isDevMode } from '@angular/core';

import {
  monitoringConfigFromEnvironment,
  monitoringEnabled,
} from '../monitoring/monitoring.config';
import { prefersConstrainedDelivery } from '../offline/delivery';
import { isBrowserOnline, subscribeOnlineStatus } from '../offline/network';

const MONITORING_IDLE_TIMEOUT_MS = 2_000;
const ANALYTICS_IDLE_TIMEOUT_MS = 4_000;

function scheduleIdle(work: () => void, timeoutMs: number): void {
  if (typeof window === 'undefined') {
    return;
  }
  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(work, { timeout: timeoutMs });
    return;
  }
  globalThis.setTimeout(work, timeoutMs);
}

/** Run `work` now if online; otherwise once when connectivity returns. */
function whenOnline(work: () => void): void {
  if (isBrowserOnline()) {
    work();
    return;
  }
  const unsub = subscribeOnlineStatus((online) => {
    if (!online) {
      return;
    }
    unsub();
    work();
  });
}

export function scheduleVercelAnalytics(): void {
  const localHosts = new Set(['localhost', '127.0.0.1', '[::1]']);
  if (typeof window === 'undefined' || localHosts.has(window.location.hostname)) {
    return;
  }
  if (prefersConstrainedDelivery()) {
    return;
  }
  const mode = isDevMode() ? 'development' : 'production';
  scheduleIdle(() => {
    whenOnline(() => {
      void Promise.all([import('@vercel/analytics'), import('@vercel/speed-insights')]).then(
        ([{ inject: injectAnalytics }, { injectSpeedInsights }]) => {
          injectAnalytics({ mode });
          injectSpeedInsights({ framework: 'angular' });
        },
      );
    });
  }, ANALYTICS_IDLE_TIMEOUT_MS);
}

async function initializeMonitoring(): Promise<void> {
  const configuration = monitoringConfigFromEnvironment();
  if (!configuration) {
    return;
  }
  try {
    const { initializeMonitoring: initializeMonitoringFacade } =
      await import('../monitoring/monitoring.facade');
    await initializeMonitoringFacade(configuration);
  } catch (error: unknown) {
    const { scrubValue } = await import('../monitoring/scrub');
    console.error('Monitoring initialization failed:', scrubValue(error));
  }
}

export function scheduleMonitoringInitialization(): void {
  if (!monitoringEnabled() || typeof window === 'undefined') {
    return;
  }
  if (prefersConstrainedDelivery()) {
    return;
  }
  scheduleIdle(() => {
    whenOnline(() => {
      void initializeMonitoring();
    });
  }, MONITORING_IDLE_TIMEOUT_MS);
}
