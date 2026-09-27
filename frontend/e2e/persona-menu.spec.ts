import { test, expect, type Page } from '@playwright/test';
import {
  mockRestRoutes,
  reachReadySession,
  pushForeignPose,
  CHARACTER,
  NYX,
} from './support/gameHarness';

/**
 * #4030 demo-fidelity review, Severe finding: the Look dialog
 * (`frontend/src/game/persona-menu/LookDialog.tsx`, a non-modal Radix
 * `Dialog`) closed itself ~150-200ms after opening, from both the right-click
 * `ContextMenu` and the left-click `DropdownMenu`, independent of network
 * timing. Cause: the closing menu's default behavior returns focus to its
 * trigger, which lands outside the just-opened Dialog; the Dialog's
 * `DismissableLayer` reads that as an outside interaction and dismisses
 * itself right back. jsdom never reproduces this (no async focus timing for
 * the two layers to race on), so `PersonaMenu.test.tsx`/`LookDialog.test.tsx`
 * stayed green through the whole bug — this spec, against a real Chromium in
 * the production build, is the regression guard those suites cannot be.
 *
 * FIXTURE-BACKED: REST is mocked via `page.route()` (both the game-entry
 * surface, via `mockRestRoutes`, and the two persona-menu-specific endpoints
 * this spec adds) and the game WebSocket via `gameHarness`'s
 * `reachReadySession`/`pushForeignPose`, the same pattern every other spec
 * in this directory uses.
 */

const CHARACTER_ID = CHARACTER.character_id;
const NYX_PERSONA_ID = 99; // The persona id gameHarness's pushForeignPose sends Nyx's poses as.

const PERSONA_MENU_FIXTURE = {
  persona_id: NYX_PERSONA_ID,
  is_self: false,
  scene_id: 1,
  viewer_persona_id: 7,
  notice: '',
  items: [{ key: 'look', label: 'Look', group: 'perception', available: true, reason: '' }],
  groups: [{ key: 'perception', empty_state: '' }],
  scene_actions: [],
};

const LOOK_RESULT = {
  backend: 'registry',
  deferred: false,
  success: true,
  message: 'A weary traveler, cloak still damp from the rain.',
};

async function mockPersonaMenuRoutes(page: Page): Promise<void> {
  // Registered AFTER mockRestRoutes's catch-all `**/api/**`, so these two
  // more specific routes take priority (Playwright runs the most recently
  // registered matching route first).
  await page.route(
    `**/api/actions/characters/${CHARACTER_ID}/personas/${NYX_PERSONA_ID}/menu/`,
    async (route) => {
      await route.fulfill({ json: PERSONA_MENU_FIXTURE });
    }
  );
  await page.route(`**/api/actions/characters/${CHARACTER_ID}/dispatch/`, async (route) => {
    await route.fulfill({ json: LOOK_RESULT });
  });
}

test.describe('PersonaMenu -> Look dialog (#4030)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
  });

  test('right-click opens Look; the dialog survives past the old auto-dismiss window, Esc closes it, and dragging moves it', async ({
    page,
  }) => {
    await mockRestRoutes(page);
    await mockPersonaMenuRoutes(page);
    const [connection] = await reachReadySession(page);
    pushForeignPose(connection);

    const pose = page.locator('[data-testid="pose-unit"]').filter({ hasText: NYX.name });
    await expect(pose).toBeVisible();
    const nameButton = pose.getByRole('button', { name: NYX.name, exact: true });

    await nameButton.click({ button: 'right' });
    const menu = page.getByRole('menu');
    await expect(menu).toBeVisible();
    await menu.getByRole('menuitem', { name: 'Look', exact: true }).click();

    const dialog = page.getByRole('dialog', { name: NYX.name });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(LOOK_RESULT.message);

    // The bug's own window was ~150-200ms; 1s is the regression guard, not a
    // flaky pad -- proving the dialog is still there well past it.
    await page.waitForTimeout(1000);
    await expect(dialog).toBeVisible();

    // Dragging by the title bar still works with the fix in place.
    const before = await dialog.boundingBox();
    if (!before) throw new Error('Look dialog has no bounding box');
    const handle = page.getByTestId('look-dialog-handle');
    const handleBox = await handle.boundingBox();
    if (!handleBox) throw new Error('Look dialog handle has no bounding box');
    await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(handleBox.x + 80, handleBox.y + 40, { steps: 5 });
    await page.mouse.up();
    const after = await dialog.boundingBox();
    if (!after) throw new Error('Look dialog lost its bounding box after dragging');
    expect(after.x).not.toBe(before.x);
    expect(after.y).not.toBe(before.y);

    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();
  });

  test('left-click on the pose name also opens Look, and the dialog stays open past the old auto-dismiss window', async ({
    page,
  }) => {
    await mockRestRoutes(page);
    await mockPersonaMenuRoutes(page);
    const [connection] = await reachReadySession(page);
    pushForeignPose(connection);

    const pose = page.locator('[data-testid="pose-unit"]').filter({ hasText: NYX.name });
    await expect(pose).toBeVisible();
    const nameButton = pose.getByRole('button', { name: NYX.name, exact: true });

    await nameButton.click();
    const menu = page.getByRole('menu');
    await expect(menu).toBeVisible();
    await menu.getByRole('menuitem', { name: 'Look', exact: true }).click();

    const dialog = page.getByRole('dialog', { name: NYX.name });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(LOOK_RESULT.message);

    await page.waitForTimeout(1000);
    await expect(dialog).toBeVisible();
  });
});
