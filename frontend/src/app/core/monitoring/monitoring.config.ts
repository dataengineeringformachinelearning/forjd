/**
 * Single builder for browser monitoring config from Angular `environment`.
 * Presentation layers must not assemble DSN/token objects inline.
 */

import { environment } from '../../../environments/environment';

import type { MonitoringConfiguration } from './monitoring.facade';

export function monitoringEnabled(): boolean {
  return Boolean(environment.sentryDsn || environment.rollbarAccessToken);
}

export function monitoringConfigFromEnvironment(): MonitoringConfiguration | null {
  if (!monitoringEnabled()) {
    return null;
  }
  return {
    dsn: environment.sentryDsn,
    rollbarAccessToken: environment.rollbarAccessToken,
    environment: environment.production ? 'production' : 'development',
  };
}
