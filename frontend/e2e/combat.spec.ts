import { test, expect } from '@playwright/test';

test.describe('Combat scene smoke tests', () => {
  test('combat scene route mounts without errors', async ({ page }) => {
    // Use a non-existent scene id; the page should render its empty/loading state
    // without crashing — that's the smoke contract.
    const errors: string[] = [];
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => errors.push(err.message));

    await page.goto('/scenes/999999/combat');
    await page.waitForLoadState('networkidle');

    const root = page.locator('#root');
    await expect(root).not.toBeEmpty();

    // Filter expected API failures (404 on the non-existent scene/encounter — these are
    // network errors, not JS exceptions).
    const unexpectedErrors = consoleErrors.filter(
      (e) => !e.includes('Failed to load resource') && !e.includes('favicon')
    );
    expect(errors).toEqual([]);
    expect(unexpectedErrors).toEqual([]);
  });

  test('combat route does not load blank page', async ({ page }) => {
    await page.goto('/scenes/1/combat');
    const root = page.locator('#root');
    await expect(root).not.toBeEmpty();
  });

  test('no uncaught JS exceptions on combat route', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => {
      exceptions.push(err.message);
    });

    await page.goto('/scenes/999999/combat');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
  });
});
