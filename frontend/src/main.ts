import { bootstrapApplication } from '@angular/platform-browser';

import { App } from './app/app';
import { appConfig } from './app/app.config';
import {
  scheduleMonitoringInitialization,
  scheduleVercelAnalytics,
} from './app/core/bootstrap/idle-integrations';
import { scrubValue } from './app/core/monitoring/scrub';

bootstrapApplication(App, appConfig)
  .then(() => {
    scheduleVercelAnalytics();
    scheduleMonitoringInitialization();
  })
  .catch((err) => console.error(scrubValue(err)));
