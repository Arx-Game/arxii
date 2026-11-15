import { test, expect, type Page } from '@playwright/test';

/**
 * The site name opens the home page from inside the world, and the character
 * stays in the world (#5137), against a live server (no mocked /api/**).
 *
 * Signs in as e2e_channels_reader, whose character "Linnea Channelwright" the
 * real-test workflow seeds for the channels spec (`seed_channels_spec`); this
 * spec runs after that one and changes nothing it reads. Runs with
 * `--config e2e.backend.config.ts`.
 *
 * Presence is a server fact (ADR-4321), so the journey reads it from the
 * server at each step: `session_count` and `room_name` on
 * `GET /api/roster/entries/mine/`, which count the sessions puppeting the
 * character. The fixture-backed twin is `selected-character-chip.spec.ts`.
 */

const CHARACTER = 'Linnea Channelwright';

interface Presence {
  session_count: number;
  room_name: string | null;
}

async function logIn(page: Page) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill('e2e_channels_reader');
  await page.getByPlaceholder('Password').fill('TestPass123!');
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

/** What the server says about the character's sessions right now. */
async function serverPresence(page: Page): Promise<Presence> {
  const res = await page.request.get('/api/roster/entries/mine/');
  expect(res.ok()).toBe(true);
  const body: unknown = await res.json();
  const rows = (Array.isArray(body) ? body : (body as { results: unknown[] }).results) as Array<
    Presence & { name: string }
  >;
  const row = rows.find((entry) => entry.name === CHARACTER);
  expect(row, `${CHARACTER} is one of the account's characters`).toBeTruthy();
  return { session_count: row!.session_count, room_name: row!.room_name };
}

async function shot(page: Page, step: string) {
  await page.screenshot({ path: test.info().outputPath(`home-${step}.png`), fullPage: false });
}

test.describe('home page while connected (#5137), live server', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('the site name opens the home page, the character stays in the world, and the chip leads back', async ({
    page,
  }) => {
    await logIn(page);
    await page.goto('/game');
    await page
      .locator(
        `button[title="Connect as ${CHARACTER}"], button[title="Switch to ${CHARACTER}"], ` +
          `button[title="${CHARACTER}"], button:has-text("${CHARACTER}")`
      )
      .first()
      .click({ timeout: 30000 });
    await expect(page.getByText('In world', { exact: true })).toBeVisible({ timeout: 30000 });

    await expect.poll(async () => (await serverPresence(page)).session_count).toBeGreaterThan(0);
    const inGame = await serverPresence(page);
    expect(inGame.room_name).toBeTruthy();

    // The site name, from inside the world.
    await page.getByRole('link', { name: 'ARX II', exact: true }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('heading', { name: 'Your Attention' })).toBeVisible({
      timeout: 15000,
    });
    const header = page.getByRole('banner');
    await expect(header.getByText(/In the world/)).toBeVisible();
    await expect(header.getByRole('link', { name: /return to the world/i })).toBeVisible();
    await expect(header.getByRole('button', { name: /disconnect character/i })).toBeVisible();
    // The server still has the same sessions on her, in the same room.
    expect(await serverPresence(page)).toEqual(inGame);
    await shot(page, '01-home-while-connected');

    // Back in: the same connection, so no session was added or dropped.
    await header.getByRole('link', { name: /return to the world/i }).click();
    await expect(page).toHaveURL(/\/game$/);
    await expect(page.getByText('In world', { exact: true })).toBeVisible({ timeout: 30000 });
    expect(await serverPresence(page)).toEqual(inGame);
    await shot(page, '02-back-in-the-world');
  });

  test('/hall is no longer an address', async ({ page }) => {
    await logIn(page);
    await page.goto('/hall');
    await expect(page.getByRole('heading', { name: '404 - Page Not Found' })).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByRole('link', { name: 'Return home' })).toHaveAttribute('href', '/');
    await shot(page, '03-hall-not-found');
  });
});
