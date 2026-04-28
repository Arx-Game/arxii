/**
 * Phase 5 smoke tests — Bulletin board and notification surfaces.
 *
 * The bulletin board lives inside TableDetailPage (/tables/:id) — the
 * bulletin section is not a standalone route. We verify the containing page
 * renders without crash.
 *
 * MuteSettingsPage (/narrative/mute-settings) is the dedicated notification
 * mute management page introduced in Wave 9.
 *
 * Run against the Vite preview build (no Django backend), so:
 * - All API calls fail with network errors (no backend running).
 * - Pages must render their shell / empty-state / error-boundary gracefully.
 * - ProtectedRoute redirects unauthenticated users to /login; either the
 *   page heading or the login heading must be visible — no JS crash.
 *
 * Full happy-path tests (authenticated user, fixture data, actual bulletin
 * posts) belong in the integration test suite once stable seeding exists.
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
// TableDetailPage (contains the bulletin section) — /tables/:id
// ---------------------------------------------------------------------------

test.describe('Phase 5 Bulletin — TableDetailPage contains bulletin section', () => {
  test('table detail page renders without JS crash (bulletin host)', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/tables/1');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('no unexpected console errors on table detail page', async ({ page }) => {
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

  test('page renders meaningful content (heading or redirect)', async ({ page }) => {
    await page.goto('/tables/1');
    await page.waitForLoadState('networkidle');

    // Without auth, ProtectedRoute redirects to /login. Either the table
    // detail heading or the login heading must be visible — both confirm
    // the React app is rendering correctly.
    await expect(page.locator('#root')).not.toBeEmpty();
    await expect(page.locator('h1').first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// MuteSettingsPage — /narrative/mute-settings
// ---------------------------------------------------------------------------

test.describe('Phase 5 Bulletin — MuteSettingsPage (/narrative/mute-settings)', () => {
  test('page shell renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/narrative/mute-settings');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('no unexpected console errors on mute-settings', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
        errors.push(msg.text());
      }
    });

    await page.goto('/narrative/mute-settings');
    await page.waitForLoadState('networkidle');

    expect(errors).toEqual([]);
  });

  test('no JS chunk failures on mute-settings', async ({ page }) => {
    const failedAssets: string[] = [];
    page.on('response', (response) => {
      if (response.url().includes('/assets/') && response.status() >= 400) {
        failedAssets.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/narrative/mute-settings');
    await page.waitForLoadState('networkidle');

    expect(failedAssets).toEqual([]);
  });

  test('page renders heading or redirect without crash', async ({ page }) => {
    await page.goto('/narrative/mute-settings');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#root')).not.toBeEmpty();
    await expect(page.locator('h1').first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Cross-cutting: bulletin + mute routes are reachable without crashes
// ---------------------------------------------------------------------------

test.describe('Phase 5 Bulletin — route navigation', () => {
  test('can visit bulletin and mute routes without uncaught exceptions', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    const routes = ['/tables/1', '/tables/2', '/narrative/mute-settings'];

    for (const route of routes) {
      await page.goto(route);
      await page.waitForLoadState('networkidle');
    }

    expect(exceptions).toEqual([]);
  });

  test('all Phase 5 routes together have no uncaught exceptions', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    // Comprehensive cross-Phase-5 route visit.
    const routes = [
      '/tables',
      '/tables/1',
      '/stories/eras',
      '/stories/browse',
      '/stories/my-offers',
      '/narrative/mute-settings',
    ];

    for (const route of routes) {
      await page.goto(route);
      await page.waitForLoadState('networkidle');
    }

    expect(exceptions).toEqual([]);
  });
});
