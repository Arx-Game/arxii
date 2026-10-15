import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Browser, type Page } from '@playwright/test';

/**
 * Evidence-challenge round 1 for #4354, against a real server seeded by seed_4354.py,
 * seed_admin.py and seed_round1.py. Not a CI spec. Scene 1 holds a proposal restated by a
 * botched terms roll; scene 2 is a story beat run with nobody seated, proposed on arrival.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4354', 'round1');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);
const PASSWORD = 'TestPass123!';

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

test('round1 web: terms botch, gloss edit, hold, shake, steady, beat-opened standoff', async ({
  browser,
}) => {
  test.setTimeout(240_000);

  // Scene 1, GM: the proposal now states the botched terms.
  const gm = await signIn(browser, 'gm4354');
  await gm.goto('/scenes/1');
  const prompt = gm.getByTestId('gm-prompt-row').first();
  await expect(prompt).toContainText('Critical failure on terms (counts as a provocation).', {
    timeout: 20_000,
  });
  await gm.screenshot({ path: shot('r1-01-gm-terms-botch-prompt.png'), fullPage: true });

  // Player: the read cause shows its authored gloss.
  const player = await signIn(browser, 'tamsin4354');
  await player.goto('/scenes/1');
  await expect(player.getByText('PLACEHOLDER Orders gloss (seeded)')).toBeVisible({
    timeout: 20_000,
  });
  await player.screenshot({ path: shot('r1-02-player-gloss-before.png'), fullPage: true });

  // Staff edit the gloss in admin; the player's card shows the new text after a reload.
  const staff = await signIn(browser, 'staff4354');
  await staff.goto('/admin/arxii/standoffcausegloss/');
  await staff.getByRole('link', { name: 'Orders', exact: true }).click();
  await staff.fill('#id_text', 'PLACEHOLDER Orders gloss (edited in admin)');
  await staff.screenshot({ path: shot('r1-03-admin-gloss-edit.png'), fullPage: true });
  await staff.click('input[name="_save"]');
  await expect(staff.getByText(/was changed successfully/)).toBeVisible();
  await player.reload();
  await expect(player.getByText('PLACEHOLDER Orders gloss (edited in admin)')).toBeVisible({
    timeout: 20_000,
  });
  await player.screenshot({ path: shot('r1-04-player-gloss-after.png'), fullPage: true });

  // GM: hold, then shake and steady with reasons.
  await prompt.getByRole('button', { name: /Hold for one action/ }).click();
  await expect(gm.getByTestId('gm-prompt-row')).toHaveCount(0, { timeout: 20_000 });
  await gm.getByTestId('rail-tab-gm').click();
  const panel = gm.getByTestId('gm-standoff-panel');
  for (const [button, reason, expected] of [
    ['Shake', 'Test reason: shake', /Falter/i],
    ['Steady', 'Test reason: steady', /80|51 \(steady\)/],
  ] as const) {
    await gm.getByRole('button', { name: button, exact: true }).first().click();
    const confirm = gm.getByTestId('standoff-morale-confirm');
    await confirm.getByRole('textbox').fill(reason);
    await confirm.getByRole('button', { name: button, exact: true }).click();
    await expect(panel).toContainText(expected, { timeout: 20_000 });
    await expect(confirm).toHaveCount(0, { timeout: 20_000 });
  }
  await expect(panel).toContainText('(steady)');
  await gm.screenshot({ path: shot('r1-05-gm-after-shake-and-steady.png'), fullPage: true });
  await player.reload();
  await expect(player.getByText('Gate Sellswords steadies.').first()).toBeVisible({
    timeout: 20_000,
  });
  await player.screenshot({ path: shot('r1-06-player-steadies-line.png'), fullPage: true });

  // Scene 2: the story beat opened a standoff; the force test proposed on arrival.
  const gmB = await signIn(browser, 'gmb4354');
  await gmB.goto('/scenes/2');
  const promptB = gmB.getByTestId('gm-prompt-row').first();
  await expect(promptB).toContainText('Ferry Toll Guards: cause fires', { timeout: 20_000 });
  await expect(promptB).toContainText('The party does not outweigh them by their margin.');
  await gmB.getByTestId('rail-tab-gm').click();
  await expect(gmB.getByTestId('gm-standoff-panel')).toContainText('Ferry Toll Guards');
  await gmB.screenshot({ path: shot('r1-07-gm-beat-opened-standoff.png'), fullPage: true });
});

test('round1 after telnet: the confirmed scene-2 proposal started round one', async ({
  browser,
}) => {
  const gmB = await signIn(browser, 'gmb4354');
  const list = await gmB.request.get('/api/combat/?scene=2');
  const encounterId = (await list.json()).results[0].id;
  const detail = await (await gmB.request.get(`/api/combat/${encounterId}/`)).json();
  console.log(
    `scene 2 encounter ${encounterId}: round_number=${detail.round_number} ` +
      `initiated_by_pc_side=${detail.initiated_by_pc_side} gm_standoff=${JSON.stringify(detail.gm_standoff)}`
  );
  expect(detail.round_number).toBe(1);
  expect(detail.gm_standoff).toBeNull();
  await gmB.goto('/scenes/2');
  await gmB.waitForTimeout(3000);
  await gmB.screenshot({ path: shot('r1-08-gm-scene2-after-confirm.png'), fullPage: true });
});
