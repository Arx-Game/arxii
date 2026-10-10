import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page } from '@playwright/test';
import { mockRestRoutes, reachReadySession, NYX, type Connection } from '../support/gameHarness';

/**
 * Review evidence for #4129 (the conversation rail): the real `/game` on the
 * production bundle, REST and the socket answered by the shared harness's
 * fixtures. The six screens of the approved demo, in order: the rail and its
 * groups; a picked row; the person row's two menus; find; the right sidebar
 * with Here and History only; the narrow pane toggle. Plus the folded strip.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4129');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const BRAM = { id: 31, name: 'Bram', thumbnail_url: '' };

function sendInteraction(connection: Connection, body: Record<string, unknown>): void {
  connection.route.send(
    JSON.stringify([
      'interaction',
      [],
      {
        timestamp: new Date().toISOString(),
        scene_id: 1,
        place_id: null,
        place_name: null,
        receiver_persona_ids: [],
        target_persona_ids: [],
        ...body,
      },
    ])
  );
}

/** The demo's fixture conversations: a room pose, a whisper from Nyx, tabletalk at the long table, a page from Bram. */
async function seedConversations(connection: Connection): Promise<void> {
  sendInteraction(connection, {
    id: 901,
    persona: { id: 99, name: NYX.name, thumbnail_url: '' },
    content: 'glances toward the noise, unhurried.',
    line: 'Nyx glances toward the noise, unhurried.',
    mode: 'pose',
  });
  sendInteraction(connection, {
    id: 902,
    persona: BRAM,
    content: 'deals the cards, one short.',
    line: 'At the long table, Bram deals the cards, one short.',
    mode: 'pose',
    place_id: 5,
    place_name: 'The long table',
  });
  sendInteraction(connection, {
    id: 903,
    persona: { id: 99, name: NYX.name, thumbnail_url: '' },
    content: 'Meet me by the east gate after.',
    line: 'Nyx whispers, "Meet me by the east gate after."',
    mode: 'whisper',
    receiver_persona_ids: [7],
  });
  connection.route.send(
    JSON.stringify([
      'text',
      ['Bram pages: Are you around for the Sunday scene?'],
      { type: 'page', from_persona_id: BRAM.id, from_name: BRAM.name },
    ])
  );
}

const rail = (page: Page) => page.getByRole('complementary', { name: 'Conversations' });

test.describe('the conversation rail (#4129)', () => {
  test.beforeEach(async ({ page }) => {
    await mockRestRoutes(page);
  });

  test('screens 1 to 5 and the folded strip at 1280 wide', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const connections = await reachReadySession(page);
    await seedConversations(connections[0]);

    // Screen 1: All on top, Here with the room, Nyx (whisper) and The long
    // table (tabletalk), OOC Pages with Bram; counts on the right.
    const aside = rail(page);
    await expect(aside.getByRole('button', { name: 'All' })).toHaveAttribute(
      'aria-current',
      'true'
    );
    const here = aside.getByTestId('rail-here');
    await expect(here.getByRole('button', { name: /^Quiet courtyard/ })).toBeVisible();
    await expect(here.getByRole('button', { name: /^Nyx\s+whisper/ })).toBeVisible();
    await expect(here.getByRole('button', { name: /^The long table\s+tabletalk/ })).toBeVisible();
    const pages = aside.getByTestId('rail-pages');
    await expect(pages.getByRole('button', { name: /^Bram\s+page/ })).toBeVisible();
    await expect(
      here.getByRole('button', { name: /^Nyx\s+whisper/ }).getByTestId('rail-count')
    ).toHaveText('1');
    await expect(
      pages.getByRole('button', { name: /^Bram\s+page/ }).getByTestId('rail-count')
    ).toHaveText('1');
    await expect(aside.getByTestId('feed-find')).toBeVisible();
    await expect(page.getByTestId('rail-resize')).toHaveAttribute('aria-valuemin', '200');
    await expect(page.getByTestId('rail-resize')).toHaveAttribute('aria-valuemax', '320');
    // Screen 5: the sidebar has Here and History, no Conversations; no tab strip.
    const modes = page.getByRole('navigation', { name: 'Sidebar modes' });
    await expect(modes.getByRole('button')).toHaveText(['Here', 'History']);
    await expect(page.getByRole('tablist', { name: 'Conversations' })).toHaveCount(0);
    await page.screenshot({ path: shot('rail-all-1280.png'), fullPage: true });

    // Screen 2: pick Nyx. The feed is the whisper alone, the count clears, the
    // composer reads Whisper → Nyx.
    await here.getByRole('button', { name: /^Nyx\s+whisper/ }).click();
    await expect(here.getByRole('button', { name: /^Nyx\s+whisper/ })).toHaveAttribute(
      'aria-current',
      'true'
    );
    await expect(page.getByText('Meet me by the east gate after.')).toBeVisible();
    await expect(page.getByText('glances toward the noise, unhurried.')).toHaveCount(0);
    await expect(page.getByText('Whisper → Nyx')).toBeVisible();
    await expect(
      here.getByRole('button', { name: /^Nyx\s+whisper/ }).getByTestId('rail-count')
    ).toHaveCount(0);
    await page.screenshot({ path: shot('rail-picked-nyx-1280.png'), fullPage: true });

    // A page row addresses the composer to its correspondent and shows the page alone.
    await pages.getByRole('button', { name: /^Bram\s+page/ }).click();
    await expect(page.getByText('Page → Bram')).toBeVisible();
    // A page reaches its correspondent wherever they stand: no table-talk refusal.
    await expect(page.getByText(/will not see table talk/)).toHaveCount(0);
    await expect(page.getByText(/Are you around for the Sunday scene/)).toBeVisible();
    await expect(page.getByText('Meet me by the east gate after.')).toHaveCount(0);
    // A row is read once it has been on screen a moment, like a thread.
    await expect(
      pages.getByRole('button', { name: /^Bram\s+page/ }).getByTestId('rail-count')
    ).toHaveCount(0);
    await page.screenshot({ path: shot('rail-picked-bram-1280.png'), fullPage: true });

    // Screen 3: a person's row. The face is a left-click menu; right-click the
    // row is the information-flow menu.
    const nyxRow = here.getByTestId('rail-row').filter({ hasText: 'Nyx' });
    await expect(
      nyxRow.getByTestId('rail-face').getByRole('button', { name: 'Nyx' })
    ).toBeVisible();
    await nyxRow.click({ button: 'right' });
    const menu = page.getByRole('menu');
    await expect(menu.getByRole('menuitem')).toHaveText([
      'Minimize all from Nyx',
      'Hide all from Nyx',
      'Expand all',
      'Unhide all',
    ]);
    // Let the menu's open transition settle so the capture is legible.
    await expect.poll(async () => menu.evaluate((el) => getComputedStyle(el).opacity)).toBe('1');
    await page.waitForTimeout(250);
    await page.screenshot({ path: shot('rail-person-menu-1280.png'), fullPage: true });
    await page.keyboard.press('Escape');
    await expect(menu).toHaveCount(0);

    // Back to All, then Screen 4: find "gate" narrows the feed within All and
    // the chips, matches marked; Esc clears; no match is one quiet line.
    await aside.getByRole('button', { name: 'All' }).click();
    await expect(page.getByText('glances toward the noise, unhurried.')).toBeVisible();
    const find = aside.getByTestId('feed-find');
    await find.fill('gate');
    await expect(page.getByText('glances toward the noise, unhurried.')).toHaveCount(0);
    await expect(page.locator('mark[data-find-match]').first()).toHaveText('gate');
    await page.screenshot({ path: shot('rail-find-1280.png'), fullPage: true });
    await find.fill('zzzz');
    await expect(page.getByTestId('feed-find-empty')).toHaveText(
      'Nothing in this session says that.'
    );
    await page.screenshot({ path: shot('rail-find-empty-1280.png'), fullPage: true });
    await find.press('Escape');
    await expect(find).toHaveValue('');
    await expect(page.getByText('glances toward the noise, unhurried.')).toBeVisible();

    // « folds the rail to a strip of counts; a count reopens it on that row.
    await aside.getByRole('button', { name: 'Collapse the rail' }).click();
    await expect(aside).toHaveAttribute('data-collapsed', 'true');
    const strip = aside.getByTestId('rail-strip');
    await expect(strip.getByTestId('rail-count')).toHaveCount(1);
    await page.screenshot({ path: shot('rail-collapsed-1280.png'), fullPage: true });
    // The one count left is the long table's; pressing it reopens the rail on that row.
    await strip.getByRole('button').first().click();
    await expect(aside).not.toHaveAttribute('data-collapsed', 'true');
    await expect(page.getByText('TT → The long table')).toBeVisible();

    expect(errors).toEqual([]);
  });

  test('screen 6: below 960px the pane toggle is Rail / Story / Sidebar', async ({ page }) => {
    // The harness reads the "In world" status, which the top bar hides below
    // `sm`; reach the ready state wide and then narrow the viewport.
    await page.setViewportSize({ width: 1280, height: 800 });
    const connections = await reachReadySession(page);
    await seedConversations(connections[0]);
    await page.setViewportSize({ width: 390, height: 844 });
    const nav = page.getByRole('navigation', { name: 'Play panes' });
    await expect(nav.getByRole('button')).toHaveText(['Rail', 'Story', 'Sidebar']);
    await nav.getByRole('button', { name: 'Rail' }).click();
    await expect(rail(page).getByRole('button', { name: /^Nyx\s+whisper/ })).toBeVisible();
    await page.screenshot({ path: shot('rail-pane-390.png'), fullPage: true });
    await rail(page)
      .getByRole('button', { name: /^Nyx\s+whisper/ })
      .click();
    await nav.getByRole('button', { name: 'Story' }).click();
    await expect(page.getByText('Whisper → Nyx')).toBeVisible();
  });
});
