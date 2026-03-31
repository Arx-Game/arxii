import { test, expect } from '@playwright/test';

test.describe('Production build smoke tests', () => {
  test('homepage loads and React app renders', async ({ page }) => {
    await page.goto('/');
    // The React app mounts into #root — if the bundle is broken, #root stays empty
    const root = page.locator('#root');
    await expect(root).not.toBeEmpty();
  });

  test('no console errors on homepage', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Filter out expected noise (favicon 404, API calls that fail without Django)
    const unexpectedErrors = errors.filter(
      (e) => !e.includes('favicon') && !e.includes('Failed to load resource')
    );
    expect(unexpectedErrors).toEqual([]);
  });

  test('no uncaught JS exceptions on homepage', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => {
      exceptions.push(err.message);
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
  });

  test('events list page renders', async ({ page }) => {
    await page.goto('/events');
    const root = page.locator('#root');
    await expect(root).not.toBeEmpty();
  });

  test('login page renders', async ({ page }) => {
    await page.goto('/login');
    const root = page.locator('#root');
    await expect(root).not.toBeEmpty();
    // Login form should be present
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });

  test('unknown route shows not found page', async ({ page }) => {
    await page.goto('/this-route-does-not-exist');
    const root = page.locator('#root');
    await expect(root).not.toBeEmpty();
  });

  test('all JS chunks load without network errors', async ({ page }) => {
    const failedRequests: string[] = [];
    page.on('response', (response) => {
      if (response.url().includes('/assets/') && response.status() >= 400) {
        failedRequests.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    expect(failedRequests).toEqual([]);
  });
});
