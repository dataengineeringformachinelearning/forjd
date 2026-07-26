import { defineConfig, devices } from '@playwright/test';

/**
 * Critical-path e2e for the public landing (prefs + onboarding checklist).
 * Starts `ng serve` via webServer when BASE_URL is unset.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env['CI'],
  retries: process.env['CI'] ? 1 : 0,
  workers: 1,
  reporter: process.env['CI'] ? 'github' : 'list',
  use: {
    baseURL: process.env['BASE_URL'] ?? 'http://127.0.0.1:4200',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env['BASE_URL']
    ? undefined
    : {
        command: 'npx ng serve --host 127.0.0.1 --port 4200',
        url: 'http://127.0.0.1:4200',
        reuseExistingServer: !process.env['CI'],
        timeout: 180_000,
      },
});
