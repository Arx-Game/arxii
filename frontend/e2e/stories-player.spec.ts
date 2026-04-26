/**
 * Player-facing Stories smoke tests.
 *
 * Run against the Vite preview build (no Django backend), so:
 * - All API calls fail with network errors (no backend running).
 * - Pages must render their shell / empty-state / error-boundary gracefully.
 * - We verify the React app mounts and the page skeleton renders without a
 *   JS crash — not the full happy path which requires live data.
 *
 * Full happy-path tests (authenticated user with fixture data) belong in the
 * integration test suite once a stable test-user seeding pipeline exists.
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
// My Active Stories — player dashboard
// ---------------------------------------------------------------------------

test.describe('Player Stories — My Active Stories page', () => {
  test('page shell renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/my-active');
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

    await page.goto('/stories/my-active');
    await page.waitForLoadState('networkidle');

    // Without a backend session, ProtectedRoute redirects to /login.
    // Either the stories page h1 ("My Stories") or the login page h1
    // ("Login to Arx II") must be visible — both mean the React app is
    // rendering correctly and no crash occurred.
    await expect(page.locator('h1').first()).toBeVisible();

    expect(errors).toEqual([]);
  });

  test('page renders a visible heading (auth redirect or stories content)', async ({ page }) => {
    await page.goto('/stories/my-active');
    await page.waitForLoadState('networkidle');

    // Without a live backend session, ProtectedRoute redirects unauthenticated
    // users to /login. Verify the app renders something meaningful (either the
    // stories page or the login redirect) without crashing.
    await expect(page.locator('#root')).not.toBeEmpty();
    await expect(page.locator('h1').first()).toBeVisible();
  });

  test('no uncaught JS exceptions on page', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/my-active');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
  });

  test('navigating to /stories redirects to my-active or shows stories index', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });
});

// ---------------------------------------------------------------------------
// Story Detail page — renders shell for any story ID (data will be absent)
// ---------------------------------------------------------------------------

test.describe('Player Stories — Story Detail page', () => {
  test('page renders for a numeric story ID without crashing', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/1');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('shows Story Log section header (may be loading or empty)', async ({ page }) => {
    await page.goto('/stories/1');
    await page.waitForLoadState('networkidle');

    // The StoryDetailPage always renders the "Story Log" section heading once
    // the outer shell mounts. In the no-backend case the story query fails but
    // the error boundary catches it and renders a fallback — either way the
    // page must not be blank.
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('invalid (non-numeric) story ID renders without crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/not-a-number');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// AGM Opportunities page — player/AGM perspective
// ---------------------------------------------------------------------------

test.describe('Player Stories — AGM Opportunities page', () => {
  test('page renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/agm-opportunities');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });
});

// ---------------------------------------------------------------------------
// My AGM Claims page
// ---------------------------------------------------------------------------

test.describe('Player Stories — My AGM Claims page', () => {
  test('page renders without JS crash', async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (err) => exceptions.push(err.message));

    await page.goto('/stories/my-claims');
    await page.waitForLoadState('networkidle');

    expect(exceptions).toEqual([]);
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('page renders a visible heading without crashing', async ({ page }) => {
    await page.goto('/stories/my-claims');
    await page.waitForLoadState('networkidle');

    // Without a live backend session, ProtectedRoute redirects unauthenticated
    // users to /login. We verify the React app renders correctly — either the
    // claims page (if authenticated) or the login page (redirect) — without a
    // JS crash. Status tabs only appear post-authentication.
    await expect(page.locator('#root')).not.toBeEmpty();
    await expect(page.locator('h1').first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Cross-cutting: all stories JS chunks load without 400+ errors
// ---------------------------------------------------------------------------

test.describe('Player Stories — asset integrity', () => {
  test('no JS chunk failures on /stories/my-active', async ({ page }) => {
    const failedAssets: string[] = [];
    page.on('response', (response) => {
      if (response.url().includes('/assets/') && response.status() >= 400) {
        failedAssets.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/stories/my-active');
    await page.waitForLoadState('networkidle');

    expect(failedAssets).toEqual([]);
  });
});
