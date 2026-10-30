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

  test('the name that opens the line carries the same two menus as the avatar (#4791)', async ({
    page,
  }) => {
    const [connection] = await reachReadySession(page);
    pushForeignPose(connection, {
      id: 905,
      content: 'leans back.',
      line: 'Nyx leans back.',
    });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText('leans back.')).toBeVisible();
    const name = line.getByTestId('pose-actor').getByRole('button', { name: 'Nyx' });
    await expect(name).toBeVisible();

    // The right button is the sorting menu at once, not the fold: the line is still there.
    await name.click({ button: 'right' });
    await expect(page.getByRole('menu').getByRole('menuitem').first()).toHaveText('Minimize');
    await expect(line.getByText('leans back.')).toBeVisible();
    await page.screenshot({ path: `${OUT}/name-sorting-menu-1600.png` });
    await page.keyboard.press('Escape');
    await expect(page.getByRole('menu')).toHaveCount(0);

    await name.click();
    const play = page.getByRole('menu');
    await expect(play.getByRole('menuitem').first()).toHaveText('Reply');
    await expect(play.getByRole('menuitem').nth(1)).toHaveText('Kudos');
    await expect(play.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await expect(play.getByRole('menuitem', { name: 'View sheet' })).toBeVisible();
    await page.screenshot({ path: `${OUT}/name-play-menu-1600.png` });
  });

  test('in the quiet room the name carries the persona menu and the sorting menu too (#4791)', async ({
    page,
  }) => {
    const [connection] = await reachReadySession(page, { scene: false });
    pushForeignPose(connection, {
      id: 906,
      content: 'sets the cup down.',
      line: 'Nyx sets the cup down.',
      sceneId: null,
    });
    const line = page.getByTestId('ambient-line').first();
    await expect(line.getByText('sets the cup down.')).toBeVisible();
    const name = line.getByTestId('pose-actor').getByRole('button', { name: 'Nyx' });

    await name.click({ button: 'right' });
    await expect(page.getByRole('menu').getByRole('menuitem').first()).toHaveText('Minimize');
    await expect(line.getByText('sets the cup down.')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('menu')).toHaveCount(0);

    await name.click();
    const play = page.getByRole('menu');
    await expect(play.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await expect(play.getByRole('menuitem', { name: 'View sheet' })).toBeVisible();
    await page.screenshot({ path: `${OUT}/quiet-room-name-play-menu-1600.png` });
  });

  test("a companion pose's name opens the owner's menu, as its avatar does (#4791)", async ({
    page,
  }) => {
    const [connection] = await reachReadySession(page);
    pushForeignPose(connection, {
      id: 907,
      content: 'pads in and settles by the fire.',
      line: 'Fang pads in and settles by the fire.',
      attributedCompanionId: 5,
      attributedCompanionName: 'Fang',
    });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText('pads in and settles by the fire.')).toBeVisible();
    await expect(line.getByText('(via Nyx)')).toBeVisible();

    await line.getByTestId('pose-actor').getByRole('button', { name: 'Fang' }).click();
    const play = page.getByRole('menu');
    // The menu is the owner's: headed Nyx, with her Reply, Kudos, Look and View sheet.
    await expect(play.getByText('Nyx', { exact: true })).toBeVisible();
    await expect(play.getByRole('menuitem').first()).toHaveText('Reply');
    await expect(play.getByRole('menuitem').nth(1)).toHaveText('Kudos');
    await expect(play.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await expect(play.getByRole('menuitem', { name: 'View sheet' })).toBeVisible();
    await page.screenshot({ path: `${OUT}/companion-name-play-menu-1600.png` });
  });

  test('a double-click on the name adds the target to the composer, as the avatar does (#4791)', async ({
    page,
  }) => {
    // #4793: the modal play menu opens on the first press and locks pointer events,
    // so the second press lands outside it and only dismisses it; the dblclick's
    // target is the page root and the wrapper's handler never runs. The avatar has
    // had this since #4128 and the name mirrors it. Expected to fail until #4793
    // settles how add-target and the menu share the button; drop this line then.
    test.fail();
    const [connection] = await reachReadySession(page);
    pushForeignPose(connection, { id: 908, content: 'leans back.', line: 'Nyx leans back.' });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText('leans back.')).toBeVisible();

    await line.getByTestId('pose-actor').getByRole('button', { name: 'Nyx' }).dblclick();
    await expect(page.getByRole('menu')).toHaveCount(0);
    await expect(page.getByRole('textbox')).toHaveValue('@Nyx');
  });

  test('a read-only line from History renders the name plain, with no menu (#4791)', async ({
    page,
  }) => {
    // Registered after the harness's catch-all, so these win (history-threads.spec.ts).
    await page.route('**/api/play/conversations/**', (route) =>
      route.fulfill({
        json: {
          results: [
            {
              ref: { kind: 'room', key: 'scene:412' },
              title: 'Scene 412',
              availability: 'retained',
              canRead: true,
              canSend: false,
              sceneId: '412',
              latestVisiblePose: { id: '11', timestamp: '2026-06-14T10:00:00Z' },
              unread: 0,
              directUnread: 0,
            },
          ],
          before: null,
          after: null,
          snapshot: '2026-06-14T12:00:00Z',
        },
      })
    );
    await page.route('**/api/play/threads/**', (route) =>
      route.fulfill({
        json: {
          results: [
            {
              id: 'a1',
              conversation: { kind: 'room', key: 'scene:412' },
              root: { id: '11', timestamp: '2026-06-14T10:00:00Z' },
              firstVisible: { id: '11', timestamp: '2026-06-14T10:00:00Z' },
              latestVisible: { id: '11', timestamp: '2026-06-14T10:00:00Z' },
              opening: 'Nyx leans back.',
              visiblePoseCount: 1,
              unread: 0,
              directUnread: 0,
            },
          ],
          before: null,
          after: null,
          snapshot: '2026-06-14T12:00:00Z',
        },
      })
    );
    await page.route('**/api/play/context/**', (route) =>
      route.fulfill({
        json: {
          results: [
            {
              id: 11,
              thread_id: 'a1',
              persona: { id: 30, name: 'Nyx' },
              content: 'leans back.',
              line: 'Nyx leans back.',
              mode: 'pose',
              visibility: 'default',
              timestamp: '2026-06-14T10:00:00Z',
              scene: 412,
              reactions: [],
              is_favorited: false,
              place: null,
              place_name: null,
              receiver_persona_ids: [],
              target_persona_ids: [],
              action_links: [],
              pose_kind: 'standard',
              endorsee_sheet_id: null,
              endorsable_resonances: [],
              pose_endorsers: [],
              my_pose_endorsement: null,
              entry_endorsers: [],
              entry_endorsed_by_me: false,
            },
          ],
          threadId: 'a1',
          before: null,
          after: null,
        },
      })
    );
    await reachReadySession(page);

    await page
      .getByRole('navigation', { name: 'Sidebar modes' })
      .getByRole('button', { name: 'History', exact: true })
      .click();
    const historyNav = page.getByTestId('history-navigator');
    const row = historyNav.locator('.mt-2.rounded.border.p-2').filter({ hasText: 'Scene 412' });
    await row.getByRole('button', { name: /^Threads$/ }).click();
    await row.getByRole('button', { name: /Nyx leans back/ }).click();
    await expect(page.getByText(/Reading history/)).toBeVisible();

    const feed = page.getByTestId('feed-scroll-container');
    const line = feed.getByTestId('pose-unit').filter({ hasText: 'leans back.' });
    await expect(line).toBeVisible();
    await expect(line.getByTestId('pose-actor')).toHaveCount(0);
    await expect(line.getByTestId('pose-avatar').getByRole('button')).toHaveCount(0);
    await line.getByText('Nyx', { exact: true }).click();
    await expect(page.getByRole('menu')).toHaveCount(0);
    await page.screenshot({ path: `${OUT}/read-only-name-1600.png` });
  });
});
