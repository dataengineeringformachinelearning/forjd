import { expect, test } from '@playwright/test';

/**
 * End-to-end critical paths on the public FORJD landing.
 * Soft chrome only — no sealed ingest or service tokens in the browser.
 */
test.describe('Landing critical paths', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      try {
        localStorage.clear();
      } catch {
        // ignore
      }
    });
    await page.route('**/ready', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        // Probe accepts status === 'ready' (see ready-probe.ts).
        body: JSON.stringify({ status: 'ready' }),
      });
    });
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'FORJD', level: 1 })).toBeVisible();
  });

  test('shows brand, docs CTAs, and partner integrate sequence', async ({ page }) => {
    await expect(page.getByText('Sealed streaming for partners')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'How partners integrate' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link')).toHaveCount(
      2,
    );
    await expect(page.locator('forjd-search-palette')).toHaveCount(0);
    await expect(page.locator('forjd-preferences')).toHaveCount(0);
    await expect(page.locator('forjd-onboarding-checklist')).toHaveCount(0);
    await expect(page.locator('.landing__capabilities')).toHaveCount(0);
  });

  test('footer exposes api, ready, docs, and legal only', async ({ page }) => {
    const footer = page.locator('footer.landing__meta');
    await expect(footer.getByText('api', { exact: true })).toBeVisible();
    await expect(footer.getByText('ready', { exact: true })).toBeVisible();
    await expect(footer.getByText('docs', { exact: true })).toBeVisible();
    await expect(footer.getByText('legal', { exact: true })).toBeVisible();
    await expect(footer.getByText('suite', { exact: true })).toHaveCount(0);
  });
});
