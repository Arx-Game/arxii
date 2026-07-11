import { test, expect } from '@playwright/test';

test.describe('Battle map smoke tests', () => {
  test('battle map route mounts without errors', async ({ page }) => {
    // Use a non-existent scene id; the page should render its empty/loading state
    // without crashing — that's the smoke contract (mirrors combat.spec.ts).
    const errors: string[] = [];
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => errors.push(err.message));

    await page.goto('/scenes/999999/battle');
    await page.waitForLoadState('networkidle');

    const root = page.locator('#root');
    await expect(root).not.toBeEmpty();

    const unexpectedErrors = consoleErrors.filter(
      (e) => !e.includes('Failed to load resource') && !e.includes('favicon')
    );
    expect(errors).toEqual([]);
    expect(unexpectedErrors).toEqual([]);
  });

  test('battle map route does not load a blank page', async ({ page }) => {
    await page.goto('/scenes/1/battle');
    const root = page.locator('#root');
    await expect(root).not.toBeEmpty();
  });

  test('no uncaught JS exceptions on the battle map route', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => {
      exceptions.push(err.message);
    });

    await page.goto('/scenes/999999/battle');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
  });
});
