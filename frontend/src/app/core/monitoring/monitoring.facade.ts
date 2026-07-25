// --- Sentry + Rollbar browser monitoring ---
import { captureException, consoleLoggingIntegration, init } from '@sentry/angular';
import type Rollbar from 'rollbar';

export interface MonitoringConfiguration {
  dsn: string;
  environment: 'production' | 'development';
  rollbarAccessToken?: string;
}

let initializationPromise: Promise<boolean> | null = null;
let rollbarClient: Rollbar | null = null;

const runInitialization = async (configuration: MonitoringConfiguration): Promise<boolean> => {
  try {
    if (configuration.dsn) {
      init({
        dsn: configuration.dsn,
        environment: configuration.environment,
        integrations: [consoleLoggingIntegration({ levels: ['log', 'warn', 'error'] })],
        enableLogs: true,
        tracesSampleRate: configuration.environment === 'production' ? 0.1 : 0,
      });
    }

    const rollbarToken = configuration.rollbarAccessToken?.trim();
    if (rollbarToken) {
      const { default: RollbarCtor } = await import('rollbar');
      rollbarClient = new RollbarCtor({
        accessToken: rollbarToken,
        captureUncaught: true,
        captureUnhandledRejections: true,
        environment: configuration.environment,
      });
    }

    return Boolean(configuration.dsn || rollbarToken);
  } catch (error: unknown) {
    console.error('Monitoring initialization failed:', error);
    return false;
  }
};

export const initializeMonitoring = (configuration: MonitoringConfiguration): Promise<boolean> => {
  initializationPromise ??= runInitialization(configuration);
  return initializationPromise;
};

export const captureMonitoringException = async (
  error: unknown,
  configuration: MonitoringConfiguration,
): Promise<void> => {
  const initialized = await initializeMonitoring(configuration);
  if (!initialized) {
    return;
  }

  try {
    if (configuration.dsn) {
      captureException(error);
    }
    const original =
      error && typeof error === 'object' && 'originalError' in error
        ? (error as { originalError?: unknown }).originalError
        : error;
    const payload = original ?? error;
    if (payload instanceof Error) {
      rollbarClient?.error(payload);
    } else {
      rollbarClient?.error(String(payload));
    }
  } catch {
    // Monitoring must never create a second application failure.
  }
};
