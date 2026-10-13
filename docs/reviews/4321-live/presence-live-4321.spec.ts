import { test, expect, type Page } from '@playwright/test';
import path from 'node:path';

/**
 * #4321 LIVE evidence: nothing here is mocked. One Chromium context (shared
 * cookies, like two tabs) against a running Evennia server on :4001 whose
 * database holds one account with one character. Tab A enters the world over
 * the real WebSocket; tab B is a cold /hall load with no socket of its own.
 *
 * Answers the evidence challenge's items 1, 3, 4, 6, 7 and 8 on PR #4324.
 * Run with the backend config: `npx playwright test --config e2e.backend.config.ts e2e/presence-live-4321.spec.ts`.
 * Throwaway: deleted from the branch after the run (real-testing skill, section 6).
 */

const SHOTS = path.join('..', 'docs', 'reviews', '4321-live');
const USERNAME = 'e2e_test_account';
const PASSWORD = 'TestPass123!';
const CHARACTER = 'Presence Tester';
const ROOM = "The Wanderer's Rest";

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="text"]').first().fill(USERNAME);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]', { hasText: /log in/i }).click();
  await expect(page).not.toHaveURL(/\/login(?:$|[?/#])/);
}

interface MineRow {
  name: string;
  session_count: number;
  room_name: string | null;
}

async function mine(page: Page): Promise<MineRow[]> {
  const response = await page.request.get('/api/roster/entries/mine/');
  expect(response.status()).toBe(200);
  return (await response.json()) as MineRow[];
}

test.describe('presence is a server fact, live (#4321)', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('one session, two tabs: the payload, the menus, and a disconnect from the tab without a socket', async ({
    browser,
  }) => {
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const a = await context.newPage();
    await login(a);

    // Out of the world: the server says so.
    const before = await mine(a);
    console.log('mine before entering:', JSON.stringify(before));
    expect(before).toHaveLength(1);
    expect(before[0].name).toBe(CHARACTER);
    expect(before[0].session_count).toBe(0);
    expect(before[0].room_name).toBeNull();

    // Tab A enters the world over the real socket. A fresh account has no
    // durable selection, so the game offers its characters; picking one
    // selects it and opens the socket (GameTopBar.handleSelectCharacter).
    await a.goto('/game');
    const picker = a.getByText('Choose a character above to begin.');
    const needsPick = await picker.waitFor({ state: 'visible', timeout: 4_000 }).then(
      () => true,
      () => false
    );
    if (needsPick) await a.getByRole('button', { name: CHARACTER }).first().click();
    await expect(a.getByText('In world', { exact: true })).toBeVisible({ timeout: 30_000 });

    // Item 1: the live server reports the session and the room.
    const live = await mine(a);
    console.log('mine in the world:', JSON.stringify(live));
    expect(live[0].session_count).toBe(1);
    expect(live[0].room_name).toBe(ROOM);

    // Item 8: no form switcher for a character with no alternate self.
    await expect(a.getByTitle('Shift into an alternate self')).toHaveCount(0);
    await a.screenshot({ path: path.join(SHOTS, 'a-game-top-bar-1280.png'), fullPage: false });

    // Item 6: the world menu's words.
    await a.getByRole('button', { name: 'Open world menu' }).click();
    await expect(a.getByRole('menuitem', { name: 'Disconnect Character' })).toBeVisible();
    await expect(a.getByRole('menuitem', { name: 'Log Out Account' })).toBeVisible();
    await expect(a.getByRole('menuitem', { name: /leave the world/i })).toHaveCount(0);
    await a.waitForTimeout(400); // let Radix's fade-in finish before the shot
    await a.screenshot({ path: path.join(SHOTS, 'a-world-menu-1280.png'), fullPage: false });
    await a.keyboard.press('Escape');

    // Item 7: your own name in the Who tab opens the account menu.
    await a.getByRole('button', { name: 'Who', exact: true }).click();
    await a
      .locator('li', { hasText: CHARACTER })
      .getByRole('button', { name: CHARACTER })
      .click();
    await expect(a.getByRole('menuitem', { name: 'Profile' })).toBeVisible();
    await expect(a.getByRole('menuitem', { name: 'Log Out Account' })).toBeVisible();
    await a.waitForTimeout(400);
    await a.screenshot({ path: path.join(SHOTS, 'a-who-tab-account-menu-1280.png'), fullPage: false });
    await a.keyboard.press('Escape');

    // Tab B: a cold /hall with no socket of its own.
    const b = await context.newPage();
    await b.goto('/hall');
    const header = b.getByRole('banner');
    await expect(header.getByText(`In the world, ${ROOM}`)).toBeVisible({ timeout: 15_000 });
    await expect(header.getByRole('link', { name: /return to the world/i })).toHaveAttribute(
      'href',
      '/game'
    );
    await expect(header.getByRole('button', { name: /disconnect character/i })).toBeVisible();
    // The Hall card is not asserted here: a staff-minted character renders in
    // the Hall's GM tile, which carries no presence line. The card reads the
    // same hook as the chip and is covered by the fixture journey and its test.
    await b.screenshot({ path: path.join(SHOTS, 'b-fresh-tab-in-the-world-1280.png'), fullPage: false });

    // Item 6: the profile dropdown's last item.
    const user = (await (await b.request.get('/api/user/')).json()) as { display_name: string };
    console.log('account display name:', user.display_name);
    await header.getByRole('button', { name: user.display_name, exact: true }).click();
    await expect(b.getByRole('menuitem', { name: 'Log Out Account' })).toBeVisible();
    await expect(b.getByRole('menuitem', { name: /^logout$/i })).toHaveCount(0);
    await b.screenshot({ path: path.join(SHOTS, 'b-profile-dropdown-1280.png'), fullPage: false });
    await b.keyboard.press('Escape');

    // Items 3 and 4: Disconnect Character from the tab without a socket closes
    // the other tab's live session on the real server.
    const [response] = await Promise.all([
      b.waitForResponse((r) => /\/api\/roster\/entries\/\d+\/disconnect\/$/.test(r.url())),
      header.getByRole('button', { name: /disconnect character/i }).click(),
    ]);
    const body = await response.text();
    console.log('disconnect response:', response.status(), body);
    expect(response.status()).toBe(200);
    expect(JSON.parse(body)).toEqual({ closed: 1 });
    await expect(b.getByRole('menuitem')).toHaveCount(0);

    // Tab A's socket was closed by the server with the quit reason: it leaves
    // the world and lands on the Hall, as a typed quit does.
    await expect(a).toHaveURL(/\/hall$/, { timeout: 20_000 });

    await expect
      .poll(async () => (await mine(b))[0].session_count, { timeout: 20_000 })
      .toBe(0);
    const after = await mine(b);
    console.log('mine after disconnect:', JSON.stringify(after));
    expect(after[0].room_name).toBeNull();

    await expect(header.getByText(/Not in the world/)).toBeVisible({ timeout: 20_000 });
    await expect(header.getByRole('link', { name: /enter the world/i })).toHaveAttribute(
      'href',
      '/game'
    );
    await b.screenshot({ path: path.join(SHOTS, 'b-after-disconnect-1280.png'), fullPage: false });
    await a.screenshot({ path: path.join(SHOTS, 'a-after-disconnect-1280.png'), fullPage: false });
    await context.close();
  });
});
