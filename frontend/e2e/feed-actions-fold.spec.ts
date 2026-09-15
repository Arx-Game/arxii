import { test, expect } from '@playwright/test';
import { mockRestRoutes, reachReadySession } from './support/gameHarness';

// #3856 PR 3: the Here panel keeps every control it has and its nine reference
// sections move under an "Actions" fold at the foot of the room view, open by
// default; a section opens in place of the room with a way back that names
// the room (demo v5, screen 8). REST and the socket are fixtures through the
// shared harness; the sidebar, the fold and the sections are the real ones.

test.describe('the Actions fold in the Here panel (#3856)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockRestRoutes(page);
  });

  test('screen 8: the fold sits under the room sections, opens a section, and comes back', async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await reachReadySession(page);

    const here = page.getByTestId('play-sidebar-scroll');
    // Every room section is still there, above the fold.
    await expect(here.getByText('Quiet courtyard', { exact: true }).first()).toBeVisible();
    await expect(here.getByText('Characters (2)')).toBeVisible();
    await expect(here.getByRole('button', { name: /Tehom\s+you/i })).toBeVisible();
    await expect(here.getByText('Exits', { exact: true })).toBeVisible();

    const fold = here.getByTestId('actions-fold');
    await expect(fold).toHaveAttribute('open', '');
    const names = await fold.getByRole('button').allTextContents();
    expect(names.map((n) => n.trim())).toEqual([
      'Who',
      'Stories',
      'Events',
      'Codex',
      'Status',
      'Items',
      'Journal',
      'Travel',
    ]);
    // The old tab row above the room is gone.
    await expect(page.getByRole('tab')).toHaveCount(0);
    await page.screenshot({ path: '../docs/reviews/3856/actions-fold-1280.png', fullPage: true });

    // A section opens in place of the room, with the way back naming the room.
    await fold.getByRole('button', { name: 'Status' }).click();
    const back = here.getByRole('button', { name: /Quiet courtyard/ });
    await expect(back).toBeVisible();
    await expect(here.getByText('Characters (2)')).toHaveCount(0);
    // The fold stays under the section with the open one marked, so the next
    // section is one press away.
    await expect(fold.getByRole('button', { name: 'Status' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await fold.getByRole('button', { name: 'Journal' }).click();
    await expect(fold.getByRole('button', { name: 'Journal' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect(back).toBeVisible();
    await page.screenshot({
      path: '../docs/reviews/3856/actions-section-1280.png',
      fullPage: true,
    });

    await back.click();
    await expect(here.getByText('Characters (2)')).toBeVisible();
    await expect(here.getByTestId('actions-fold')).toBeVisible();

    // The fold closes on its arrow and opens again.
    await fold.getByText('Actions').click();
    await expect(fold).not.toHaveAttribute('open', '');
    await expect(fold.getByRole('button', { name: 'Who' })).toBeHidden();
    await page.screenshot({
      path: '../docs/reviews/3856/actions-fold-closed-1280.png',
      fullPage: true,
    });
    await fold.getByText('Actions').click();
    await expect(fold.getByRole('button', { name: 'Who' })).toBeVisible();

    expect(errors).toEqual([]);
  });
});
