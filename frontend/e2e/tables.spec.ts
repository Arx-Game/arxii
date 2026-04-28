/**
 * Phase 5 smoke tests — Tables pages.
 *
 * Run against the Vite preview build (no Django backend), so:
 * - All API calls fail with network errors (no backend running).
 * - Pages must render their shell / empty-state / error-boundary gracefully
 *   without crashing — especially the graceful-403 fallback for GM-only
 *   sections, and error boundaries for failed API fetches.
 * - We verify JS chunks load, React mounts, and key structural elements are
 *   present without requiring a live authenticated session.
 *
 * Full happy-path tests (GM user with fixture data) belong in the integration
 * test suite once stable test-user seeding exists.
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
// TablesListPage — /tables
// ---------------------------------------------------------------------------

test.describe('Phase 5 — TablesListPage (/tables)', () => {
  test('page shell renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/tables');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('page heading is visible (or login redirect)', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
        errors.push(msg.text());
      }
    });

    await page.goto('/tables');
    await page.waitForLoadState('networkidle');

    // Without a backend session, ProtectedRoute redirects to /login.
    // Either the tables page heading or the login page heading must be visible.
    await expect(page.locator('h1').first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('no uncaught JS exceptions on /tables', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/tables');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
  });

  test('no unexpected console errors on /tables', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
        errors.push(msg.text());
      }
    });

    await page.goto('/tables');
    await page.waitForLoadState('networkidle');

    expect(errors).toEqual([]);
  });

  test('no JS chunk failures on /tables', async ({ page }) => {
    const failedAssets: string[] = [];
    page.on('response', (response) => {
      if (response.url().includes('/assets/') && response.status() >= 400) {
        failedAssets.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/tables');
    await page.waitForLoadState('networkidle');

    expect(failedAssets).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// TableDetailPage — /tables/:id
// ---------------------------------------------------------------------------

test.describe('Phase 5 — TableDetailPage (/tables/:id)', () => {
  test('page renders for a numeric table ID without crashing', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/tables/1');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('no unexpected console errors on /tables/1', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
        errors.push(msg.text());
      }
    });

    await page.goto('/tables/1');
    await page.waitForLoadState('networkidle');

    expect(errors).toEqual([]);
  });

  test('invalid (non-numeric) table ID renders without crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/tables/not-a-number');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
  });

  test('no JS chunk failures on /tables/1', async ({ page }) => {
    const failedAssets: string[] = [];
    page.on('response', (response) => {
      if (response.url().includes('/assets/') && response.status() >= 400) {
        failedAssets.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/tables/1');
    await page.waitForLoadState('networkidle');

    expect(failedAssets).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Cross-cutting: tables routes are reachable without uncaught exceptions
// ---------------------------------------------------------------------------

test.describe('Phase 5 — tables route navigation', () => {
  test('can visit all tables routes without uncaught exceptions', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    const routes = ['/tables', '/tables/1', '/tables/999'];

    for (const route of routes) {
      await page.goto(route);
      await page.waitForLoadState('networkidle');
    }

    expect(exceptions).toEqual([]);
  });
});
