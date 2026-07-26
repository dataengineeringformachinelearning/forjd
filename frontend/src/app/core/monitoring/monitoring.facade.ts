// --- Sentry + Rollbar browser monitoring (landing / crash reporting only) ---
import { addBreadcrumb, captureException, consoleLoggingIntegration, init } from '@sentry/angular';
import type Rollbar from 'rollbar';

import { scrubBreadcrumb, scrubValue, type MonitoringBreadcrumb } from './scrub';

export interface MonitoringConfiguration {
  dsn: string;
  environment: 'production' | 'development';
  rollbarAccessToken?: string;
}

/** One-shot SDK init promise — not a config store; callers always pass configuration. */
let initializationPromise: Promise<boolean> | null = null;
let rollbarClient: Rollbar | null = null;

const runInitialization = async (configuration: MonitoringConfiguration): Promise<boolean> => {
  try {
    if (configuration.dsn) {
      init({
        dsn: configuration.dsn,
        environment: configuration.environment,
        integrations: [consoleLoggingIntegration({ levels: ['warn', 'error'] })],
        enableLogs: true,
        tracesSampleRate: configuration.environment === 'production' ? 0.1 : 0,
        beforeSend(event) {
          return scrubValue(event) as typeof event;
        },
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
        transform: (payload: Record<string, unknown>) => {
          const scrubbed = scrubValue(payload) as Record<string, unknown>;
          Object.keys(payload).forEach((key) => {
            delete payload[key];
          });
          Object.assign(payload, scrubbed);
        },
      });
    }

    return Boolean(configuration.dsn || rollbarToken);
  } catch (error: unknown) {
    console.error('Monitoring initialization failed:', scrubValue(error));
    return false;
  }
};

export const initializeMonitoring = (configuration: MonitoringConfiguration): Promise<boolean> => {
  initializationPromise ??= runInitialization(configuration);
  return initializationPromise;
};

type NgWrappedError = {
  readonly originalError?: unknown;
};

function isNgWrappedError(error: unknown): error is NgWrappedError {
  return typeof error === 'object' && error !== null && 'originalError' in error;
}

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
    const payload = isNgWrappedError(error) ? (error.originalError ?? error) : error;
    if (payload instanceof Error) {
      rollbarClient?.error(payload);
    } else {
      rollbarClient?.error(String(scrubValue(payload)));
    }
  } catch {
    // Monitoring must never create a second application failure.
  }
};

/** Soft-failure / ops breadcrumb — never include tokens or ciphertext. */
export const addMonitoringBreadcrumb = async (
  breadcrumb: MonitoringBreadcrumb,
  configuration: MonitoringConfiguration,
): Promise<void> => {
  const initialized = await initializeMonitoring(configuration);
  if (!initialized) {
    return;
  }

  const safe = scrubBreadcrumb(breadcrumb);
  try {
    if (configuration.dsn) {
      addBreadcrumb({
        category: safe.category,
        message: safe.message,
        level: safe.level,
        data: safe.data,
      });
    }
    if (rollbarClient && safe.level !== 'info') {
      rollbarClient.info(`[${safe.category}] ${safe.message}`, safe.data);
    }
  } catch {
    // Breadcrumbs must never create a second application failure.
  }
};
