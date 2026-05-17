/**
 * Story Author page smoke tests.
 *
 * Run against the Vite preview build (no Django backend), so:
 * - All API calls fail with network errors (no backend running).
 * - The reshaped author page (scope-assign trigger, progress banner,
 *   Tree/DAG/GM-Notes tabs, run-control + quick-add wiring) must render
 *   its shell / 403-fallback / error-boundary gracefully.
 * - We verify the React app mounts and the page skeleton renders without a
 *   JS crash — not the full happy path which requires live data.
 *
 * Full happy-path tests (Lead GM user with fixture data, editing the
 * chapter/episode/beat tree, etc.) belong in the integration test suite
 * once a stable test-user seeding pipeline exists.
 */

import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Helper — suppress expected network-error console noise from failed API calls
// ---------------------------------------------------------------------------

function filterApiNoise(msg: string): boolean {
  return (
    msg.includes('Failed to load resource') ||
    msg.includes('favicon') ||
    msg.includes('fetch') ||
    msg.includes('NetworkError') ||
    msg.includes('Load failed') ||
    // React Query logs query failures to console.error in dev builds
    msg.includes('Query data cannot be undefined') ||
    msg.includes('An update to') ||
    // Vite preview: the SPA fallback serves index.html for unknown routes,
    // but the /api/* requests 404 which logs a resource error
    msg.includes('404')
  );
}

// ---------------------------------------------------------------------------
// Story Author — CRUD editor page
// ---------------------------------------------------------------------------

test.describe('Story Author — author editor page', () => {
  test('page shell renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/author');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    // React app must have mounted
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('page heading is visible (or login redirect heading is visible)', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
        errors.push(msg.text());
      }
    });

    await page.goto('/stories/author');
    await page.waitForLoadState('networkidle');

    // Without a backend session, ProtectedRoute redirects to /login.
    // Either the author page h1 ("Story Author") or the login page h1
    // ("Login to Arx II") must be visible — both mean the React app is
    // rendering correctly and no crash occurred.
    await expect(page.locator('h1').first()).toBeVisible();

    expect(errors).toEqual([]);
  });
});
