import { isDevMode } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { inject as injectAnalytics } from '@vercel/analytics';
import { injectSpeedInsights } from '@vercel/speed-insights';

import { appConfig } from './app/app.config';
import { App } from './app/app';

const mode = isDevMode() ? 'development' : 'production';

// Framework-agnostic Vercel Web Analytics + Speed Insights (active on Vercel deploys).
injectAnalytics({ mode });
injectSpeedInsights({ framework: 'angular' });

bootstrapApplication(App, appConfig).catch((err) => console.error(err));
