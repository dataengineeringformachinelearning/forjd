// --- Global Angular ErrorHandler → Sentry/Rollbar ---
import { isPlatformBrowser } from '@angular/common';
import { ErrorHandler, Injectable, PLATFORM_ID, inject } from '@angular/core';
import { environment } from '../../../environments/environment';

@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  private readonly platformId = inject(PLATFORM_ID);

  handleError(error: unknown): void {
    void this.captureInMonitoring(error);
    console.error('GlobalErrorHandler caught an error:', error);
  }

  private async captureInMonitoring(error: unknown): Promise<void> {
    if (
      (!environment.sentryDsn && !environment.rollbarAccessToken) ||
      !isPlatformBrowser(this.platformId)
    ) {
      return;
    }

    try {
      const { captureMonitoringException } = await import('../monitoring/monitoring.facade');
      await captureMonitoringException(error, {
        dsn: environment.sentryDsn,
        rollbarAccessToken: environment.rollbarAccessToken,
        environment: environment.production ? 'production' : 'development',
      });
    } catch {
      // Error reporting must never create a second application failure.
    }
  }
}
