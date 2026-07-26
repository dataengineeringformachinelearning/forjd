// --- Global Angular ErrorHandler → monitoring + toast + chunk recovery ---
import { isPlatformBrowser } from '@angular/common';
import { ErrorHandler, Injectable, Injector, PLATFORM_ID, inject } from '@angular/core';
import { FjToastService } from 'forjd-ui';

import { isChunkLoadError, reloadOnceOnChunkError } from '../chunk-load-recovery';
import {
  monitoringConfigFromEnvironment,
  monitoringEnabled,
} from '../monitoring/monitoring.config';
import { scrubValue } from '../monitoring/scrub';
import { SHELL_STORY } from '../../shell.story';

@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly injector = inject(Injector);

  handleError(error: unknown): void {
    if (isPlatformBrowser(this.platformId) && reloadOnceOnChunkError(error)) {
      return;
    }

    void this.captureInMonitoring(error);
    // Scrub before console — Sentry consoleLoggingIntegration may forward this.
    console.error('GlobalErrorHandler caught an error:', scrubValue(error));

    if (isPlatformBrowser(this.platformId) && !isChunkLoadError(error)) {
      const toast = SHELL_STORY.unexpectedToast;
      queueMicrotask(() => {
        try {
          this.injector.get(FjToastService).show(toast.title, {
            description: toast.description,
            tone: 'danger',
            durationMs: 6000,
          });
        } catch {
          // Toast host may be unavailable during early bootstrap.
        }
      });
    }
  }

  private async captureInMonitoring(error: unknown): Promise<void> {
    if (!monitoringEnabled() || !isPlatformBrowser(this.platformId)) {
      return;
    }
    // Chunk skew storms Sentry/Rollbar; recovery reload handles it locally.
    if (isChunkLoadError(error)) {
      return;
    }

    const configuration = monitoringConfigFromEnvironment();
    if (!configuration) {
      return;
    }

    try {
      const { captureMonitoringException } = await import('../monitoring/monitoring.facade');
      await captureMonitoringException(error, configuration);
    } catch {
      // Error reporting must never create a second application failure.
    }
  }
}
