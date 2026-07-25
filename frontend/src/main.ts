import { isDevMode } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { inject as injectAnalytics } from '@vercel/analytics';
import { injectSpeedInsights } from '@vercel/speed-insights';

import { appConfig } from './app/app.config';
import { App } from './app/app';
import { environment } from './environments/environment';

const MONITORING_IDLE_TIMEOUT_MS = 2_000;
const mode = isDevMode() ? 'development' : 'production';

// --- Vercel platform analytics ---
injectAnalytics({ mode });
injectSpeedInsights({ framework: 'angular' });

// --- Sentry + Rollbar (idle-deferred) ---
const initializeMonitoring = async (): Promise<void> => {
  if (!environment.sentryDsn && !environment.rollbarAccessToken) {
    return;
  }

  try {
    const { initializeMonitoring: initializeMonitoringFacade } = await import(
      './app/core/monitoring/monitoring.facade'
    );
    await initializeMonitoringFacade({
      dsn: environment.sentryDsn,
      rollbarAccessToken: environment.rollbarAccessToken,
      environment: environment.production ? 'production' : 'development',
    });
  } catch (error: unknown) {
    console.error('Monitoring initialization failed:', error);
  }
};

const scheduleMonitoringInitialization = (): void => {
  if (
    (!environment.sentryDsn && !environment.rollbarAccessToken) ||
    typeof window === 'undefined'
  ) {
    return;
  }

  const initialize = (): void => {
    void initializeMonitoring();
  };

  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(initialize, { timeout: MONITORING_IDLE_TIMEOUT_MS });
    return;
  }

  globalThis.setTimeout(initialize, MONITORING_IDLE_TIMEOUT_MS);
};

bootstrapApplication(App, appConfig)
  .then(() => {
    scheduleMonitoringInitialization();
  })
  .catch((err) => console.error(err));
