import { test, expect, type Locator, type Page } from '@playwright/test';

/**
 * Player channels (#3299), against a live server (no mocked /api/**).
 *
 * Needs the rows `integration_tests.live_seeds.seed_channels_spec` writes for
 * e2e_test_account (the real-test workflow runs it after the server starts): the
 * account plays "Linnea Channelwright", a member of "The Lantern Guild" whose channel
 * is provisioned; "Odo Brightwater" (another player) has said one line in Public; and
 * "Mara Thornquill", whose player e2e_test_account blocks, has said one line after it.
 * Runs with `--config e2e.backend.config.ts`.
 *
 * Every assertion is on what the page shows. Settings are read back after a reload, so
 * a change the page shows but the server never kept fails here. The spec puts back what
 * it changes (mute, collapse), so it can run again against the same database.
 */

const CHARACTER = 'Linnea Channelwright';
const ORG = 'The Lantern Guild';
const OTHER_SPEAKER = 'Odo Brightwater';
const OTHER_MESSAGE = 'Evening, all. Anyone walking the lantern route tonight?';
const BLOCKED_SPEAKER = 'Mara Thornquill';
// The other players' account names; the reader's own may show in the page header.
const ACCOUNT_NAMES = ['channels_other_player', 'channels_blocked_player'];

async function logIn(page: Page) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill('e2e_test_account');
  await page.getByPlaceholder('Password').fill('TestPass123!');
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

async function shot(page: Page, step: string) {
  await page.screenshot({
    path: test.info().outputPath(`channels-${step}.png`),
    fullPage: true,
  });
}

function lane(scope: Page | Locator, name: string): Locator {
  return scope.getByRole('region', { name, exact: true });
}

function subscriptionWrite(page: Page, method: 'POST' | 'PATCH') {
  return page.waitForResponse(
    (r) => r.url().includes('/api/channels/subscriptions/') && r.request().method() === method
  );
}

/** Joins *name* from the "Join a channel" list, unless an earlier run already did. */
async function join(page: Page, name: string) {
  await expect(page.getByRole('heading', { name: 'Channels', exact: true })).toBeVisible({
    timeout: 15000,
  });
  const directory = page.getByRole('region', { name: 'Join a channel' });
  const row = directory.getByRole('listitem').filter({
    has: page.getByText(name, { exact: true }),
  });
  // Either the lane or the directory row is drawn once the channel list loads.
  await expect(lane(page, name).or(row)).toBeVisible({ timeout: 15000 });
  if (await row.isVisible()) {
    const joined = subscriptionWrite(page, 'POST');
    await row.getByRole('button', { name: 'Join', exact: true }).click();
    expect((await joined).status()).toBe(201);
  }
  await expect(lane(page, name)).toBeVisible();
}

/** Opens a lane's settings menu (a popover dialog). */
async function openSettings(page: Page, name: string): Promise<Locator> {
  await lane(page, name)
    .getByRole('button', { name: `${name} settings`, exact: true })
    .click();
  const menu = page.getByRole('dialog');
  await expect(menu.getByText('Mute', { exact: true })).toBeVisible();
  return menu;
}

/** Picks the character the account speaks as in *name*, through the settings menu. */
async function speakAs(page: Page, name: string, character: string) {
  const menu = await openSettings(page, name);
  const picker = menu.getByRole('combobox', { name: 'Speak as' });
  // The trigger is blank until the identity list loads; then it shows the chosen
  // character, or the "Speak as" placeholder when none is chosen yet. Choosing the
  // character already shown saves nothing, so read it only once it has loaded.
  await expect(picker).not.toHaveText('', { timeout: 15000 });
  if ((await picker.textContent())?.trim() !== character) {
    const saved = subscriptionWrite(page, 'PATCH');
    await picker.click();
    await page.getByRole('option', { name: character, exact: true }).click();
    expect((await saved).status()).toBe(200);
  }
  await expect(picker).toHaveText(character);
  await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);
}

async function setMute(page: Page, name: string, muted: boolean) {
  const menu = await openSettings(page, name);
  const toggle = menu.getByRole('switch', { name: 'Mute' });
  if ((await toggle.isChecked()) !== muted) {
    const saved = subscriptionWrite(page, 'PATCH');
    await toggle.click();
    expect((await saved).status()).toBe(200);
  }
  if (muted) await expect(toggle).toBeChecked();
  else await expect(toggle).not.toBeChecked();
  await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);
}

/** A lane's collapse toggle: the first header button (the settings trigger follows it). */
function laneToggle(scope: Page | Locator, name: string): Locator {
  return lane(scope, name).locator('header > button').first();
}

/** Collapses or expands a lane from its header. */
async function setCollapsed(page: Page, name: string, collapsed: boolean) {
  const header = laneToggle(page, name);
  if ((await header.getAttribute('aria-expanded')) === String(collapsed)) {
    const saved = subscriptionWrite(page, 'PATCH');
    await header.click();
    expect((await saved).status()).toBe(200);
  }
  await expect(header).toHaveAttribute('aria-expanded', String(!collapsed));
}

async function expectNoAccountNames(page: Page) {
  for (const account of ACCOUNT_NAMES) {
    await expect(page.getByText(account)).toHaveCount(0);
  }
}

test.describe.configure({ mode: 'serial' });

test.describe('player channels', () => {
  test('Public: join, speak as a character, see a blocked line hidden, mute and collapse', async ({
    page,
  }) => {
    await logIn(page);
    await page.goto('/channels');
    await shot(page, '01-directory');

    await join(page, 'Public');
    // An earlier run may have left the lane collapsed if it died midway.
    await setCollapsed(page, 'Public', false);
    await speakAs(page, 'Public', CHARACTER);

    const publicLane = lane(page, 'Public');
    const messages = publicLane.getByTestId('channel-messages');
    // The other player's line, under his character's name.
    const otherLine = messages.getByRole('listitem').filter({ hasText: OTHER_MESSAGE });
    await expect(otherLine).toBeVisible({ timeout: 15000 });
    await expect(otherLine).toContainText(OTHER_SPEAKER);
    // The blocked player's line is one "1 hidden" rule: no name, no text.
    await expect(messages.getByTestId('hidden-divider')).toHaveText('1 hidden');
    await expect(page.getByText(BLOCKED_SPEAKER)).toHaveCount(0);
    await expectNoAccountNames(page);
    await shot(page, '02-public-joined');

    // Speak, and the line appears under the chosen character's name.
    const said = `The lanterns are lit at ${Date.now()}.`;
    const posted = page.waitForResponse(
      (r) => r.url().includes('/api/channels/messages/') && r.request().method() === 'POST'
    );
    await publicLane.getByRole('textbox', { name: 'Message' }).fill(said);
    await publicLane.getByRole('button', { name: 'Send', exact: true }).click();
    expect((await posted).status()).toBe(201);
    const ownLine = messages.getByRole('listitem').filter({ hasText: said });
    await expect(ownLine).toBeVisible();
    await expect(ownLine).toContainText(CHARACTER);
    await expect(publicLane.getByRole('textbox', { name: 'Message' })).toHaveValue('');
    // Read back from the server, not the page's cache.
    await page.reload();
    await expect(
      lane(page, 'Public').getByTestId('channel-messages').getByRole('listitem').filter({
        hasText: said,
      })
    ).toContainText(CHARACTER, { timeout: 15000 });
    await shot(page, '03-public-posted');

    // Mute, and a fresh load still has it muted.
    await setMute(page, 'Public', true);
    await page.reload();
    const menu = await openSettings(page, 'Public');
    await expect(menu.getByRole('switch', { name: 'Mute' })).toBeChecked();
    await shot(page, '04-public-muted-after-reload');
    await page.keyboard.press('Escape');
    await setMute(page, 'Public', false);

    // Collapse: the messages go away, and a fresh load keeps the lane collapsed.
    await setCollapsed(page, 'Public', true);
    await expect(lane(page, 'Public').getByTestId('channel-messages')).toHaveCount(0);
    await page.reload();
    await expect(laneToggle(page, 'Public')).toHaveAttribute('aria-expanded', 'false', {
      timeout: 15000,
    });
    await expect(lane(page, 'Public').getByTestId('channel-messages')).toHaveCount(0);
    await shot(page, '05-public-collapsed');
    await setCollapsed(page, 'Public', false);
    await expect(lane(page, 'Public').getByText(OTHER_MESSAGE)).toBeVisible();
  });

  test('the org channel is listed for a member and joins as a lane', async ({ page }) => {
    await logIn(page);
    await page.goto('/channels');
    await join(page, ORG);
    await setCollapsed(page, ORG, false);
    // Only the member character can speak for the guild; pick her if the join did not.
    await speakAs(page, ORG, CHARACTER);
    const orgLane = lane(page, ORG);
    await expect(orgLane.getByRole('textbox', { name: 'Message' })).toBeVisible();
    await page.reload();
    await expect(lane(page, ORG)).toBeVisible({ timeout: 15000 });
    await expect(lane(page, 'Public')).toBeVisible();
    await expectNoAccountNames(page);
    await shot(page, '06-org-joined');
  });

  test('the play page sidebar shows the same lanes in Channels mode', async ({ page }) => {
    await logIn(page);
    await page.goto('/game');
    await page
      .locator(
        `button[title="Connect as ${CHARACTER}"], button[title="Switch to ${CHARACTER}"], ` +
          `button[title="${CHARACTER}"], button:has-text("${CHARACTER}")`
      )
      .first()
      .click({ timeout: 30000 });
    await page
      .getByRole('navigation', { name: 'Sidebar modes' })
      .getByRole('button', { name: /^Channels/ })
      .click({ timeout: 30000 });
    const sidebar = page.getByRole('complementary', { name: 'Play sidebar' });
    await expect(lane(sidebar, 'Public').getByText(OTHER_MESSAGE)).toBeVisible({
      timeout: 15000,
    });
    await expect(lane(sidebar, 'Public').getByTestId('hidden-divider')).toHaveText('1 hidden');
    await expect(lane(sidebar, ORG)).toBeVisible();
    await shot(page, '07-play-sidebar-channels');
  });
});
