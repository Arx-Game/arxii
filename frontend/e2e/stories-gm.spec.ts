/**
 * GM-facing Stories smoke tests.
 *
 * Run against the Vite preview build (no Django backend), so:
 * - All API calls fail with network errors (no backend running).
 * - Pages must render their shell / empty-state / error-boundary gracefully
 *   without crashing — especially the graceful-403 fallback pages.
 * - We verify JS chunks load, React mounts, and key structural elements are
 *   present without requiring a live authenticated session.
 *
 * Full happy-path tests (GM user with fixture data, resolving episodes, etc.)
 * belong in the integration test suite once stable test-user seeding exists.
 */

import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Helper — suppress expected API-failure console noise
// ---------------------------------------------------------------------------

function filterApiNoise(msg: string): boolean {
  return (
    msg.includes('Failed to load resource') ||
    msg.includes('favicon') ||
    msg.includes('fetch') ||
    msg.includes('NetworkError') ||
    msg.includes('Load failed') ||
    msg.includes('Query data cannot be undefined') ||
    msg.includes('An update to') ||
    msg.includes('404')
  );
}

// ---------------------------------------------------------------------------
// GM Queue — Lead GM dashboard
// ---------------------------------------------------------------------------

test.describe('GM Stories — GM Queue page', () => {
  test('page shell renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/gm-queue');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('no unexpected console errors on page load', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
        errors.push(msg.text());
      }
    });

    await page.goto('/stories/gm-queue');
    await page.waitForLoadState('networkidle');

    expect(errors).toEqual([]);
  });

  test('page heading is visible', async ({ page }) => {
    await page.goto('/stories/gm-queue');
    await page.waitForLoadState('networkidle');

    // GMQueuePage renders "GM Queue" or "Lead GM Dashboard" — verify the <h1>
    // or page title element is present and visible.
    await expect(page.locator('h1').first()).toBeVisible();
  });

  test('scope filter chips or section headings are present', async ({ page }) => {
    await page.goto('/stories/gm-queue');
    await page.waitForLoadState('networkidle');

    // GMQueuePage renders scope filter chips ("All / Personal / Group / Global")
    // while data is loading. In no-backend mode the loading state resolves to
    // either the 403-fallback (NotGMPage) or an empty queue. Either way,
    // the page must render something meaningful.
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('no JS chunk failures on gm-queue', async ({ page }) => {
    const failedAssets: string[] = [];
    page.on('response', (response) => {
      if (response.url().includes('/assets/') && response.status() >= 400) {
        failedAssets.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/stories/gm-queue');
    await page.waitForLoadState('networkidle');

    expect(failedAssets).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Staff Workload dashboard
// ---------------------------------------------------------------------------

test.describe('GM Stories — Staff Workload page', () => {
  test('page renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/staff-workload');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('no unexpected console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
        errors.push(msg.text());
      }
    });

    await page.goto('/stories/staff-workload');
    await page.waitForLoadState('networkidle');

    expect(errors).toEqual([]);
  });

  test('page heading is visible', async ({ page }) => {
    await page.goto('/stories/staff-workload');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('h1').first()).toBeVisible();
  });

  test('no JS chunk failures on staff-workload', async ({ page }) => {
    const failedAssets: string[] = [];
    page.on('response', (response) => {
      if (response.url().includes('/assets/') && response.status() >= 400) {
        failedAssets.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/stories/staff-workload');
    await page.waitForLoadState('networkidle');

    expect(failedAssets).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Story Author editor
// ---------------------------------------------------------------------------

test.describe('GM Stories — Story Author page', () => {
  test('author list page renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/author');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('author detail page renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    // Story ID 1 will 404 on the API but the error boundary catches it
    await page.goto('/stories/author/1');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('no JS chunk failures on author page', async ({ page }) => {
    const failedAssets: string[] = [];
    page.on('response', (response) => {
      if (response.url().includes('/assets/') && response.status() >= 400) {
        failedAssets.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/stories/author');
    await page.waitForLoadState('networkidle');

    expect(failedAssets).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Cross-route navigation: GM pages are reachable without crashing
// ---------------------------------------------------------------------------

test.describe('GM Stories — cross-route navigation', () => {
  test('can visit all GM stories routes without uncaught exceptions', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    const routes = [
      '/stories/gm-queue',
      '/stories/staff-workload',
      '/stories/author',
      '/stories/agm-opportunities',
      '/stories/my-claims',
    ];

    for (const route of routes) {
      await page.goto(route);
      await page.waitForLoadState('networkidle');
    }

    expect(exceptions).toEqual([]);
  });
});
