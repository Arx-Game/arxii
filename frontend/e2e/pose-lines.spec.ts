import { test, expect, type Locator, type Page } from '@playwright/test';
import { mockRestRoutes, pushForeignPose, reachReadySession } from './support/gameHarness';

// #4128: a pose is a prose line, and the line's controls live behind the two
// buttons. Each of these depends on layout or on real pointer timing, which
// jsdom does not have, so this runs the built page in a browser. REST and the
// socket are fixtures, the same shape as `feed-follow.spec.ts`.

const OUT = 'test-results/pose-lines';

const THREE_PARAGRAPHS =
  'Nyx does not look up when the bench takes his weight. The cup turns a quarter in her ' +
  'fingers, then another quarter, the way it has been turning since the rain started, and ' +
  'she lets the silence sit between them until it is nearly rude.\n\n' +
  '"The gate watch changed at dusk," she says at last, to the cup. "Two of them I know. The ' +
  "third I don't, and he looked at the courtyard wall for a long time, the way a man looks " +
  'at a thing he has been told to remember." Her eyes come up then, grey and unhurried, and ' +
  'stay on his face. "I\'d like to know who told him."\n\n' +
  'She sets the cup down between them. It is empty, and has been for some time.';

/** The left edge of the first rendered line of text inside `body`. */
function firstLineLeft(body: Locator): Promise<number> {
  return body.evaluate((el) => {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const text = walker.nextNode();
    if (!text) return Number.NaN;
    const range = document.createRange();
    range.selectNodeContents(text);
    return range.getClientRects()[0]?.left ?? Number.NaN;
  });
}

/** The left edge of the second rendered line of the first text node inside `body`. */
function secondLineLeft(body: Locator): Promise<number> {
  return body.evaluate((el) => {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const text = walker.nextNode();
    if (!text) return Number.NaN;
    const range = document.createRange();
    range.selectNodeContents(text);
    return range.getClientRects()[1]?.left ?? Number.NaN;
  });
}

/** The left edge of the last rendered line of text inside `body`. */
function lastLineLeft(body: Locator): Promise<number> {
  return body.evaluate((el) => {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let last: Node | null = null;
    for (let node = walker.nextNode(); node; node = walker.nextNode()) last = node;
    if (!last) return Number.NaN;
    const range = document.createRange();
    range.selectNodeContents(last);
    const rects = range.getClientRects();
    return rects[rects.length - 1]?.left ?? Number.NaN;
  });
}

async function heldRightClick(page: Page, target: Locator): Promise<void> {
  const box = await target.boundingBox();
  if (!box) throw new Error('no box');
  await page.mouse.move(box.x + 120, box.y + 8);
  await page.mouse.down({ button: 'right' });
  await page.waitForTimeout(500);
  await page.mouse.up({ button: 'right' });
}

test.describe('a pose is a prose line (#4128)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 900 });
    await mockRestRoutes(page);
    // The persona menu's server half (#4030), so the play menu renders its
    // social items and not a Loading line. Registered after the harness's
    // catch-all, so it wins.
    await page.route('**/api/actions/characters/*/personas/*/menu/', (route) =>
      route.fulfill({
        json: {
          persona_id: 9,
          is_self: false,
          scene_id: null,
          viewer_persona_id: 7,
          notice: '',
          items: [
            { key: 'look', label: 'Look', group: 'perception', available: true, reason: '' },
            { key: 'mute', label: 'Mute', group: 'social', available: true, reason: '' },
            { key: 'block', label: 'Block…', group: 'social', available: true, reason: '' },
          ],
          groups: [
            { key: 'perception', empty_state: '' },
            { key: 'social', empty_state: '' },
          ],
          scene_actions: [],
        },
      })
    );
  });

  test('the avatar is an indent: the first line starts beside it, the rest wrap back under it', async ({
    page,
  }) => {
    const [connection] = await reachReadySession(page);
    pushForeignPose(connection, { id: 901, content: THREE_PARAGRAPHS });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/told him/)).toBeVisible();

    const avatar = line.getByTestId('pose-avatar');
    const avatarBox = await avatar.boundingBox();
    if (!avatarBox) throw new Error('no avatar');
    const body = line.getByTestId('pose-body');
    expect(await firstLineLeft(body)).toBeGreaterThan(avatarBox.x + avatarBox.width);
    // An indent is the first line only: the avatar fits inside one line of text,
    // so line 2 is already flush left, not just the next paragraph.
    expect(await secondLineLeft(body)).toBeLessThan(avatarBox.x + 2);
    expect(await lastLineLeft(body)).toBeLessThan(avatarBox.x + 2);
    // No header row: nothing between the top of the line and the first text line.
    await expect(line.locator('header')).toHaveCount(0);
    // The time is there for hover, not on the page at rest.
    await expect(line.getByTestId('pose-time')).toHaveCSS('opacity', '0');
    await line.hover();
    await expect(line.getByTestId('pose-time')).toHaveCSS('opacity', '1');
    await page.screenshot({ path: `${OUT}/paragraphs-1600.png` });
  });

  test('a quick right-click folds the line; another on the stub unfolds it', async ({ page }) => {
    const [connection] = await reachReadySession(page);
    pushForeignPose(connection, { id: 902, content: 'Nyx glances toward the noise, unhurried.' });
    const text = page.getByText('Nyx glances toward the noise, unhurried.');
    await expect(text).toBeVisible();

    await text.click({ button: 'right' });
    const stub = page.locator('[data-feed-stub="i:902"]');
    await expect(stub).toBeVisible();
    await expect(text).toHaveCount(0);
    await page.screenshot({ path: `${OUT}/folded-1600.png` });

    await stub.getByRole('button', { name: /Nyx · / }).click({ button: 'right' });
    await expect(page.getByText('Nyx glances toward the noise, unhurried.')).toBeVisible();
  });

  test('a held right-click opens the sorting menu; Hide takes the line out and Show hidden brings it back', async ({
    page,
  }) => {
    const [connection] = await reachReadySession(page);
    pushForeignPose(connection, { id: 903, content: 'Nyx sets the cup down.' });
    const text = page.getByText('Nyx sets the cup down.');
    await expect(text).toBeVisible();

    await heldRightClick(page, text);
    const menu = page.getByRole('menu');
    await expect(menu).toBeVisible();
    await expect(menu.getByRole('menuitem')).toHaveText([
      'Minimize',
      'Hide',
      'Minimize all from Nyx',
      'Hide all from Nyx',
      'Minimize all',
      'Expand all',
      'Unhide all',
    ]);
    await page.screenshot({ path: `${OUT}/menu-1600.png` });
    await menu.getByRole('menuitem', { name: 'Hide', exact: true }).click();
    await expect(text).toHaveCount(0);
    await page.getByRole('button', { name: 'Show hidden' }).click();
    await expect(page.getByText('Nyx sets the cup down.')).toBeVisible();
  });

  test('a right-click on the avatar opens the same menu; a left-click opens the play menu', async ({
    page,
  }) => {
    const [connection] = await reachReadySession(page);
    pushForeignPose(connection, { id: 904, content: 'Nyx leans back.' });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText('Nyx leans back.')).toBeVisible();
    const avatar = line.getByTestId('pose-avatar');

    await avatar.click({ button: 'right' });
    await expect(page.getByRole('menu').getByRole('menuitem').first()).toHaveText('Minimize');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('menu')).toHaveCount(0);

    await avatar.getByRole('button').click();
    const play = page.getByRole('menu');
    await expect(play.getByRole('menuitem').first()).toHaveText('Reply');
    await expect(play.getByRole('menuitem').nth(1)).toHaveText('Kudos');
    await expect(play.getByRole('menuitem', { name: 'View sheet' })).toBeVisible();
    // Mute and Block stay in the play menu (left click), by ruling.
    await expect(play.getByRole('menuitem', { name: 'Mute' })).toBeVisible();
    await expect(play.getByRole('menuitem', { name: /^Block/ })).toBeVisible();
    await page.screenshot({ path: `${OUT}/play-menu-1600.png` });
  });
});
