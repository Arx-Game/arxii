import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Browser, type Page } from '@playwright/test';

/**
 * Review evidence for #4354 against a real server (rt_4354, seeded by
 * seed_4354.py): a GM, a player in the encounter and an onlooker in the scene,
 * each signed in through the real login form, on the real scene page. The
 * seed already left one GM proposal pending (a player's press botched against
 * an Orders group). Not a CI spec: it needs that seeded server on :4001.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4354');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);
const PASSWORD = 'TestPass123!';
const SCENE = '/scenes/1';

async function signIn(browser: Browser, username: string): Promise<Page> {
  const context = await browser.newContext({ viewport: { width: 1500, height: 1100 } });
  const page = await context.newPage();
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill(username);
  await page.getByPlaceholder('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'));
  return page;
}

test.describe.configure({ mode: 'serial' });

test('the GM, a player and an onlooker each see their own seat of the standoff', async ({
  browser,
}) => {
  test.setTimeout(180_000);

  // Player seat: the card marks the provoked group as deciding, nothing more.
  const player = await signIn(browser, 'tamsin4354');
  await player.goto(SCENE);
  await expect(player.getByTestId('combat-rail')).toBeVisible({ timeout: 20_000 });
  await expect(player.getByText(/deciding/i).first()).toBeVisible({ timeout: 20_000 });
  await expect(player.getByText(/Critical failure on a press/)).toHaveCount(0);
  await player.screenshot({ path: shot('01-player-deciding.png'), fullPage: true });

  // Onlooker seat: the public summary, no cause, no drive.
  const onlooker = await signIn(browser, 'oriel4354');
  await onlooker.goto(SCENE);
  await expect(onlooker.getByTestId('standoff-summary-card')).toBeVisible({ timeout: 20_000 });
  await expect(onlooker.getByTestId('standoff-summary-card')).not.toContainText('Orders');
  await expect(onlooker.getByTestId('standoff-summary-card')).not.toContainText('Greedy');
  await onlooker.screenshot({ path: shot('02-onlooker-summary.png'), fullPage: true });

  // GM seat: the prompt and the GM standoff panel.
  const gm = await signIn(browser, 'gm4354');
  await gm.goto(SCENE);
  const prompt = gm.getByTestId('gm-prompt-row').first();
  await expect(prompt).toContainText('Gate Sellswords', { timeout: 20_000 });
  await expect(prompt).toContainText('Critical failure on a press');
  await gm.getByTestId('rail-tab-gm').click();
  const panel = gm.getByTestId('gm-standoff-panel');
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expect(panel).toContainText('Orders');
  await expect(panel).toContainText('Greedy (test)');
  await gm.screenshot({ path: shot('03-gm-prompt-and-panel.png'), fullPage: true });

  // Override needs a reason; Hold for one action puts the group back to open.
  const override = prompt.getByRole('button', { name: /^Override$/ });
  await expect(override).toBeDisabled();
  await prompt.getByRole('button', { name: /Hold for one action/ }).click();
  await expect(gm.getByTestId('gm-prompt-row')).toHaveCount(0, { timeout: 20_000 });
  await gm.screenshot({ path: shot('04-gm-after-hold.png'), fullPage: true });

  // The morale control: Shake asks for a reason, then moves the group to faltering.
  await gm.getByTestId('rail-tab-gm').click();
  await gm
    .getByRole('button', { name: /^Shake$/ })
    .first()
    .click();
  const confirm = gm.getByTestId('standoff-morale-confirm');
  await expect(confirm).toBeVisible();
  await confirm.getByRole('textbox').fill('Test reason: they saw their captain leave.');
  await gm.screenshot({ path: shot('05-gm-shake-confirm.png'), fullPage: true });
  await confirm.getByRole('button', { name: /^Shake/ }).click();
  await expect(panel).toContainText(/Falter/i, { timeout: 20_000 });
  await gm.screenshot({ path: shot('06-gm-after-shake.png'), fullPage: true });

  // Everyone sees the room line, and the player no longer sees "deciding".
  await player.reload();
  await expect(player.getByText(/Gate Sellswords falters\./).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(player.getByText(/deciding/i)).toHaveCount(0);
  await player.screenshot({ path: shot('07-player-after-hold-and-shake.png'), fullPage: true });
  await onlooker.reload();
  await expect(onlooker.getByText(/Gate Sellswords falters\./).first()).toBeVisible({
    timeout: 20_000,
  });
  await onlooker.screenshot({ path: shot('08-onlooker-after-shake.png'), fullPage: true });
});

test('staff author a creature on the Standoff Profile Builder', async ({ browser }) => {
  test.setTimeout(120_000);
  const page = await signIn(browser, 'staff4354');
  // The creature's change page links to the builder.
  await page.goto('/admin/arxii/creaturetemplate/1/change/');
  await page.getByRole('link', { name: 'Open the Standoff Profile Builder' }).click();
  await expect(page.getByRole('heading', { name: 'Standoff Profile Builder' })).toBeVisible();
  await expect(page.getByText('PLACEHOLDER: wants coin more than safety')).toBeVisible();
  await page.screenshot({ path: shot('09-admin-profile-builder.png'), fullPage: true });
  // Change the margin and save; the page reloads with the stored value.
  await page.fill('#id_cause_margin_percent', '25');
  await page.click('input[name="save_continue"]');
  await expect(page.getByText('Saved and credited to you.')).toBeVisible();
  await expect(page.locator('#id_cause_margin_percent')).toHaveValue('25');
  await expect(page.getByText(/With margin 25,/)).toBeVisible();
  await page.screenshot({ path: shot('10-admin-profile-builder-saved.png'), fullPage: true });
});
