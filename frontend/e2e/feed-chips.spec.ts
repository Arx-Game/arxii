import { test, expect, type Page } from '@playwright/test';
import { mockRestRoutes, reachReadySession, type Connection, NYX } from './support/gameHarness';

// #3856 PR 2: the filter chips above the feed, All, the chip editor, custom
// chips, wake, minimise and dismiss, and per-account persistence. One journey
// per demo screen (issue #3856, demo v5). REST and the socket are fixtures
// through the shared harness; the strip, the editor, the readers and the
// preference store are the real ones.

function text(line: string, kwargs: Record<string, unknown> = {}): string {
  return JSON.stringify(['text', [line], kwargs]);
}

function interaction(id: number, mode: string, content: string, name = NYX.name): string {
  return JSON.stringify([
    'interaction',
    [],
    {
      id,
      persona: { id: 99, name, thumbnail_url: '' },
      content,
      mode,
      timestamp: new Date().toISOString(),
      scene_id: 1,
      place_id: null,
      place_name: null,
      receiver_persona_ids: [],
      target_persona_ids: [],
    },
  ]);
}

/** Seeds the demo's opening column: a pose, speech, ambience, a look note, an item line and an error. */
async function seedColumn(page: Page, connection: Connection): Promise<void> {
  connection.route.send(
    interaction(501, 'pose', 'settles onto the fountain rim, careful of the flowers.')
  );
  await expect(page.getByText(/settles onto the fountain rim/)).toBeVisible();
  connection.route.send(interaction(502, 'say', 'You picked a strange hour for the plaza.'));
  await expect(page.getByText(/strange hour for the plaza/)).toBeVisible();
  connection.route.send(
    text('The brazier pops and sends a spiral of sparks up into the shadow.', { type: 'narrative' })
  );
  connection.route.send(text('Nyx<br>A tall woman in a grey coat.', { type: 'look' }));
  connection.route.send(text('You take the brass lantern.', { type: 'item' }));
  connection.route.send(
    text('Command \'lok\' is not available. Maybe you meant "look"?', { type: 'error' })
  );
  await expect(page.getByRole('alert')).toContainText("Command 'lok' is not available.");
  // The player is reading the column: the dwell marks the poses seen, and the
  // Roleplay chip's "new" pill goes out. Screen 1 is the column at rest.
  await expect(strip(page).getByRole('button', { name: /Roleplay/ })).not.toContainText('new', {
    timeout: 5000,
  });
}

function strip(page: Page) {
  return page.getByRole('toolbar', { name: 'Feed filters' });
}

test.describe('feed filter chips (#3856)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockRestRoutes(page);
  });

  test('screens 1 to 3: the strip at rest, System pressed, All pressed', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const [connection] = await reachReadySession(page);
    await seedColumn(page, connection);

    // Screen 1: plain chips, + and All at the end; everything in the column.
    const buttons = await strip(page).getByRole('button').allTextContents();
    expect(buttons.map((b) => b.trim())).toEqual([
      'Roleplay',
      'Whispers',
      'Movement',
      'Ambience',
      'System',
      '+',
      'All',
    ]);
    await expect(page.locator('[data-testid="feed-note"]')).toHaveCount(4);
    await page.screenshot({ path: '../docs/reviews/3856/chips-rest-1280.png', fullPage: true });

    // Screen 2: System pressed folds the look, item and error out; the poses stay.
    await strip(page).getByRole('button', { name: 'System' }).click();
    await expect(page.locator('[data-testid="feed-note"][data-kind="look"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="feed-note"][data-kind="error"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="feed-note"][data-kind="ambience"]')).toHaveCount(1);
    await expect(page.getByText(/settles onto the fountain rim/)).toBeVisible();
    await page.screenshot({
      path: '../docs/reviews/3856/chips-system-off-1280.png',
      fullPage: true,
    });
    await strip(page).getByRole('button', { name: 'System' }).click();
    await expect(page.locator('[data-testid="feed-note"]')).toHaveCount(4);

    // Screen 3: All empties the column; one chip brings one kind back.
    await strip(page).getByRole('button', { name: 'All' }).click();
    await expect(page.getByTestId('feed-all-off')).toHaveText(
      'Everything is switched off. Press a chip to bring one kind back.'
    );
    await expect(strip(page).getByRole('button', { name: 'Roleplay' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    await page.screenshot({ path: '../docs/reviews/3856/chips-all-off-1280.png', fullPage: true });
    await strip(page).getByRole('button', { name: 'Roleplay' }).click();
    await expect(page.getByText(/settles onto the fountain rim/)).toBeVisible();
    await expect(page.locator('[data-testid="feed-note"]')).toHaveCount(0);
    await expect(strip(page).getByRole('button', { name: 'Ambience' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    await page.screenshot({
      path: '../docs/reviews/3856/chips-roleplay-only-1280.png',
      fullPage: true,
    });
    expect(errors).toEqual([]);
  });

  test('screens 4 and 5: the editor moves a kind, a custom chip is born, three is the cap', async ({
    page,
  }) => {
    const [connection] = await reachReadySession(page);
    await seedColumn(page, connection);

    // Screen 4: right-click Roleplay opens the editor.
    await strip(page).getByRole('button', { name: 'Roleplay' }).click({ button: 'right' });
    const editor = page.getByRole('dialog');
    await expect(editor.getByLabel('Chip name')).toHaveValue('Roleplay');
    await expect(editor.getByLabel('Whispers')).not.toBeChecked();
    await expect(editor.getByText('(in Whispers)')).toBeVisible();
    await expect(editor.getByLabel('Wake me when this arrives')).toBeChecked();
    // The popover fades in; let it settle so the shot shows it opaque.
    await page.waitForTimeout(400);
    await page.screenshot({ path: '../docs/reviews/3856/chips-editor-1280.png', fullPage: true });
    // Untick Speech: the say line stays in the column, since an unowned kind still shows.
    await editor.getByLabel('Speech').uncheck();
    await expect(page.getByText(/strange hour for the plaza/)).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);

    // Screen 5: + makes a chip, its editor opens with the name selected; Speech moves there.
    await strip(page).getByRole('button', { name: '+' }).click();
    const born = page.getByRole('dialog');
    await expect(born.getByLabel('Chip name')).toHaveValue('Chip 1');
    await expect(born.getByLabel('Chip name')).toBeFocused();
    await page.keyboard.type('Talk');
    await born.getByLabel('Speech').check();
    await page.keyboard.press('Escape');
    await expect(strip(page).getByRole('button', { name: 'Talk' })).toBeVisible();
    await strip(page).getByRole('button', { name: 'Talk' }).click();
    await expect(page.getByText(/strange hour for the plaza/)).toHaveCount(0);
    await strip(page).getByRole('button', { name: 'Talk' }).click();
    await expect(page.getByText(/strange hour for the plaza/)).toBeVisible();

    for (const name of ['Second', 'Third']) {
      await strip(page).getByRole('button', { name: '+' }).click();
      await expect(page.getByRole('dialog').getByLabel('Chip name')).toBeFocused();
      await page.keyboard.type(name);
      await page.keyboard.press('Enter');
      await expect(strip(page).getByRole('button', { name })).toBeVisible();
    }
    await expect(strip(page).getByRole('button', { name: '+' })).toHaveCount(0);
    await page.screenshot({
      path: '../docs/reviews/3856/chips-three-custom-1280.png',
      fullPage: true,
    });

    // Delete a custom chip from its editor; its kind keeps showing.
    await strip(page).getByRole('button', { name: 'Talk' }).click({ button: 'right' });
    await page.getByRole('dialog').getByRole('button', { name: 'Delete chip' }).click();
    await expect(strip(page).getByRole('button', { name: 'Talk' })).toHaveCount(0);
    await expect(page.getByText(/strange hour for the plaza/)).toBeVisible();

    // The layout survives a reload: it is the player's own, per account, per browser.
    await page.reload();
    await expect(page.getByRole('textbox')).toBeEnabled();
    await expect(strip(page).getByRole('button', { name: 'Second' })).toBeVisible();
    await expect(strip(page).getByRole('button', { name: '+' })).toBeVisible();
  });

  test('screen 6: ambience shows without waking; a pose lights the chip', async ({ page }) => {
    const [connection] = await reachReadySession(page);
    connection.route.send(
      interaction(601, 'pose', 'looks at the fountain for longer than it deserves.')
    );
    await expect(page.getByText(/longer than it deserves/)).toBeVisible();
    // Reading the pose marks it seen; wait out the dwell so the strip is quiet.
    await expect(strip(page).getByRole('button', { name: 'Roleplay' })).not.toContainText('new', {
      timeout: 5000,
    });

    connection.route.send(text('Wind moves the cut flowers on the rim.', { type: 'narrative' }));
    await expect(page.getByText('Wind moves the cut flowers on the rim.')).toBeVisible();
    await expect(strip(page).getByRole('button', { name: 'Ambience' })).not.toContainText('new');

    // A pose from someone else arrives while the column is not being read.
    await page.evaluate(() => window.dispatchEvent(new Event('blur')));
    connection.route.send(interaction(602, 'pose', 'inclines a head toward the woman on the rim.'));
    await expect(strip(page).getByRole('button', { name: /Roleplay/ })).toContainText('new');
    await page.screenshot({ path: '../docs/reviews/3856/chips-new-pill-1280.png', fullPage: true });
  });

  test('screen 7: minimise folds a block to a stub; dismiss removes it from this view', async ({
    page,
  }) => {
    const [connection] = await reachReadySession(page);
    await seedColumn(page, connection);

    const pose = page.locator('[data-feed-block="i:501"]');
    await pose.hover();
    await pose.getByRole('button', { name: 'Minimise' }).click();
    const stub = page.locator('[data-feed-stub="i:501"]');
    await expect(stub).toBeVisible();
    await expect(stub.getByRole('button').first()).toHaveText(/^Nyx · /);
    await expect(page.getByText(/settles onto the fountain rim/)).toHaveCount(0);
    await page.screenshot({
      path: '../docs/reviews/3856/chips-minimised-1280.png',
      fullPage: true,
    });

    await stub.getByRole('button').first().click();
    await expect(page.getByText(/settles onto the fountain rim/)).toBeVisible();

    const error = page.locator('[data-feed-block="n:n4"]');
    await error.hover();
    await error.getByRole('button', { name: 'Dismiss' }).click();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.locator('[data-testid="feed-note"]')).toHaveCount(3);
  });
});
