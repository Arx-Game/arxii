/**
 * Phase 5 smoke tests — Era Admin page.
 *
 * Run against the Vite preview build (no Django backend), so:
 * - All API calls fail with network errors (no backend running).
 * - Pages must render their shell / empty-state / error-boundary gracefully.
 * - Without a backend session, StaffRoute redirects to /login (or /home).
 *   Either way the page must mount without a JS crash.
 *
 * Full happy-path tests (staff user with fixture data) belong in the
 * integration test suite once stable test-user seeding exists.
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
// EraAdminPage — /stories/eras
// ---------------------------------------------------------------------------

test.describe('Phase 5 — EraAdminPage (/stories/eras)', () => {
  test('page shell renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/eras');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('page heading is visible (era admin or redirect)', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
        errors.push(msg.text());
      }
    });

    await page.goto('/stories/eras');
    await page.waitForLoadState('networkidle');

    // StaffRoute redirects unauthenticated users — verify app renders
    // something meaningful (era admin heading or login redirect).
    await expect(page.locator('#root')).not.toBeEmpty();
    await expect(page.locator('h1').first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('no uncaught JS exceptions on /stories/eras', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/eras');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
  });

  test('no unexpected console errors on /stories/eras', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
        errors.push(msg.text());
      }
    });

    await page.goto('/stories/eras');
    await page.waitForLoadState('networkidle');

    expect(errors).toEqual([]);
  });

  test('no JS chunk failures on /stories/eras', async ({ page }) => {
    const failedAssets: string[] = [];
    page.on('response', (response) => {
      if (response.url().includes('/assets/') && response.status() >= 400) {
        failedAssets.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/stories/eras');
    await page.waitForLoadState('networkidle');

    expect(failedAssets).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// BrowseStoriesPage — /stories/browse (public, no auth required)
// ---------------------------------------------------------------------------

test.describe('Phase 5 — BrowseStoriesPage (/stories/browse)', () => {
  test('page shell renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/browse');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('no unexpected console errors on /stories/browse', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
        errors.push(msg.text());
      }
    });

    await page.goto('/stories/browse');
    await page.waitForLoadState('networkidle');

    expect(errors).toEqual([]);
  });

  test('page heading is visible on /stories/browse', async ({ page }) => {
    await page.goto('/stories/browse');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#root')).not.toBeEmpty();
    await expect(page.locator('h1').first()).toBeVisible();
  });

  test('no JS chunk failures on /stories/browse', async ({ page }) => {
    const failedAssets: string[] = [];
    page.on('response', (response) => {
      if (response.url().includes('/assets/') && response.status() >= 400) {
        failedAssets.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/stories/browse');
    await page.waitForLoadState('networkidle');

    expect(failedAssets).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// MyStoryOffersPage — /stories/my-offers (GM offer inbox)
// ---------------------------------------------------------------------------

test.describe('Phase 5 — MyStoryOffersPage (/stories/my-offers)', () => {
  test('page shell renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/my-offers');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('no unexpected console errors on /stories/my-offers', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
        errors.push(msg.text());
      }
    });

    await page.goto('/stories/my-offers');
    await page.waitForLoadState('networkidle');

    expect(errors).toEqual([]);
  });

  test('no JS chunk failures on /stories/my-offers', async ({ page }) => {
    const failedAssets: string[] = [];
    page.on('response', (response) => {
      if (response.url().includes('/assets/') && response.status() >= 400) {
        failedAssets.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/stories/my-offers');
    await page.waitForLoadState('networkidle');

    expect(failedAssets).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Cross-cutting: era + browse + offers routes reachable without crashes
// ---------------------------------------------------------------------------

test.describe('Phase 5 — era/browse/offers route navigation', () => {
  test('can visit all Phase 5 stories routes without uncaught exceptions', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    const routes = ['/stories/eras', '/stories/browse', '/stories/my-offers'];

    for (const route of routes) {
      await page.goto(route);
      await page.waitForLoadState('networkidle');
    }

    expect(exceptions).toEqual([]);
  });
});
