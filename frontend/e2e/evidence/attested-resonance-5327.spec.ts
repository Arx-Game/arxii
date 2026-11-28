import { readFileSync } from 'node:fs';

import {
  test,
  expect,
  type Browser,
  type Locator,
  type Page,
  type TestInfo,
} from '@playwright/test';

/**
 * Review evidence for #5327, against a live server (no mocked /api/**), run by
 * `just shot --spec e2e/evidence/attested-resonance-5327.spec.ts` on the `rt_5327` database.
 *
 * Needs the rows `integration_tests.live_seeds.seed_attested_resonance_spec` writes for
 * e2e_test_account (the coordinator writes its result to the JSON file named by
 * ATTESTED_RESONANCE_SEED, default /tmp/attested-resonance-seed.json): the three affinities
 * with a verb, a gain fatigue and a skill each; the six resonances with their help text; an
 * award table, three strengths and the demo's seven-row weekly table; the bonus check; a live
 * scene that stores its poses, in The Lantern, with Daven (e2e_test_account), Hale, Ilsa (a
 * scene co-owner, not its GM), Brannoc and Marek (the scene's GM), each played by their own
 * account; two acts of Daven's that wait to be marked (Intimidated Hale, which suggests
 * Cruelty, and Searched the cellar, which suggests nothing); a pose of Daven's that already
 * carries a Mercy mark; a pose of Brannoc's that names no resonance; a mission whose first
 * option pays Mercy at once; and a staff account for admin.
 *
 * One named PNG per screen of the approved demo (.demos/issue-5327-attested-resonance.html),
 * each written to the test's own output folder, which `just shot` lists when the run ends.
 * Run it once per seeded database: marking Intimidated Hale uses that act up, and the seed
 * (which wipes and writes Daven's acts, grants and the scene's poses again) is what resets it.
 * Nothing here submits a journal entry or a tag; the GM undoes one reward, and the witness
 * leaves one pick waiting for the poser.
 *
 * Left out: Screen 9 (telnet, not a screen of the web app), and the frames that need a roll
 * to land on a chosen result (picking the mission option and the private line it prints), a
 * worn target (Screen 4's shrunk and refused lines) or a fifth mark in a week.
 */

const ACCOUNT = 'e2e_test_account';
const PASSWORD = 'TestPass123!';
const VIEWPORT = { width: 1440, height: 900 };
const POSE_TEXT =
  'leans over Hale until the lantern light shakes in his eyes. "Say it again. Slowly this ' +
  'time." He is smiling.';

interface Seed {
  scene_id: number;
  scene_name: string;
  daven_name: string;
  daven_sheet_id: number;
  act_intimidated_id: number;
  act_cellar_id: number;
  marked_grant_id: number;
  marked_pose_text: string;
  bell_pose_text: string;
  moment_type_label: string;
  mission_instance_id: number;
  mission_name: string;
  abyssal_affinity_id: number;
  cruelty_id: number;
  cruelty_description: string;
  mercy_description: string;
  weekly_row_count: number;
  kindling_config_id: number;
  gain_source_stat_id: number;
  player_password: string;
  witness_username: string;
  bell_poser_username: string;
  gm_username: string;
  gm_password: string;
  staff_username: string;
  staff_password: string;
}

function readSeed(): Seed {
  return JSON.parse(
    readFileSync(process.env.ATTESTED_RESONANCE_SEED ?? '/tmp/attested-resonance-seed.json', 'utf8')
  ) as Seed;
}

async function logIn(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill(username);
  await page.getByPlaceholder('Password').fill(password);
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

/** A fresh browser context signed in as one account, so each account reads on its own. */
async function signedInPage(browser: Browser, username: string, password: string): Promise<Page> {
  const context = await browser.newContext({ viewport: VIEWPORT });
  const page = await context.newPage();
  await logIn(page, username, password);
  return page;
}

/** One PNG of `target` (the page when none is given), named for the demo screen it matches. */
async function shot(
  testInfo: TestInfo,
  name: string,
  target: Page | Locator,
  options: { fullPage?: boolean } = {}
) {
  const path = testInfo.outputPath(name);
  if ('goto' in target) {
    await target.screenshot({ path, fullPage: options.fullPage ?? false });
  } else {
    await target.screenshot({ path });
  }
}

/** The pose in the feed whose text holds `text`. */
function poseWith(page: Page, text: string): Locator {
  return page.getByTestId('pose-unit').filter({ hasText: text });
}

/** The scene page, once its feed has loaded the pose Brannoc wrote. */
async function openScene(page: Page, seed: Seed) {
  await page.goto(`/scenes/${seed.scene_id}`);
  await expect(poseWith(page, 'cracked bell')).toBeVisible({ timeout: 45000 });
}

test.describe.configure({ mode: 'serial' });
test.use({ viewport: VIEWPORT });

test.describe('A character gains resonance from the acts she took (#5327)', () => {
  test('screen 6: the journal form carries the row, and an act must be chosen', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(120_000);
    const seed = readSeed();
    const page = await signedInPage(browser, ACCOUNT, PASSWORD);
    await page.goto('/journals');
    await page.getByRole('button', { name: 'Write', exact: true }).click();
    const desk = page.locator('section[aria-label="Write in your journal"]');
    await expect(desk).toBeVisible({ timeout: 30000 });
    await desk.getByLabel('Title', { exact: true }).fill('The stranger at the tollgate');
    await desk
      .getByLabel('Entry', { exact: true })
      .fill('I should have stopped sooner. I did not know his name, only that nobody else would.');

    await desk.getByTestId('reach-toggle').click();
    await desk.getByTestId('reach-select').selectOption({ label: 'Mercy' });
    await expect(desk.getByTestId('reach-help')).toHaveText(seed.mercy_description);
    const acts = desk.getByTestId('reach-acts');
    await expect(acts.getByText('Pointing at (required)', { exact: true })).toBeVisible();
    await expect(acts).toContainText('Intimidated Hale');
    await expect(acts).toContainText('Searched the cellar');
    await expect(desk.getByTestId(`reach-act-${seed.act_intimidated_id}`)).toBeVisible();
    await expect(desk.getByTestId(`reach-act-${seed.act_cellar_id}`)).toBeVisible();
    // A journal entry has no "Nothing" choice: no one can endorse a journal entry.
    await expect(desk.getByTestId('reach-act-none')).toHaveCount(0);
    // With no act chosen the entry cannot be posted.
    await expect(desk.getByRole('button', { name: 'Post entry' })).toBeDisabled();
    await desk.scrollIntoViewIfNeeded();
    await shot(testInfo, '06-journal-form-act-required.png', desk);

    await page.context().close();
  });

  test('screens 1 to 3: the mission beat, the composer with Reaching for open, and the result', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(240_000);
    const seed = readSeed();
    const page = await signedInPage(browser, ACCOUNT, PASSWORD);
    await page.goto('/game');
    await page
      .locator(
        `button[title="Connect as ${seed.daven_name}"], ` +
          `button[title="Switch to ${seed.daven_name}"], ` +
          `button[title="${seed.daven_name}"], button:has-text("${seed.daven_name}")`
      )
      .first()
      .click({ timeout: 30000 });
    // The scene's feed is loaded once Brannoc's pose is in it.
    await expect(poseWith(page, 'cracked bell')).toBeVisible({ timeout: 60000 });

    // Screen 1: the Stories section opens the beat. The option that names Mercy says what it
    // pays before she picks, with the mission theme's player text as the reason, and shows no
    // amount; the other option says nothing of the kind.
    await page.getByTestId('actions-fold').getByRole('button', { name: 'Stories' }).click();
    const row = page.getByTestId(`story-row-${seed.mission_instance_id}`);
    await row.getByRole('button', { name: seed.mission_name }).click();
    const beat = row.getByTestId('beat-card');
    await expect(beat).toBeVisible({ timeout: 30000 });
    await expect(beat.getByTestId('beat-option')).toHaveCount(2);
    await expect(beat).toContainText('Let the smugglers go and pay their fine yourself');
    await expect(beat).toContainText('Persuasion · risk 2');
    await expect(beat).toContainText('Turn them in to the tollwarden');
    await expect(beat).toContainText('Law');
    await expect(beat.getByTestId('option-feeds')).toHaveCount(1);
    await expect(beat.getByTestId('option-feeds')).toHaveText(
      'Pays you Mercy at once: This option is about sparing them.'
    );
    await row.scrollIntoViewIfNeeded();
    await shot(testInfo, '01-mission-beat-option-pays-mercy.png', row);

    // Screen 2: the composer's Reaching for row, with Cruelty chosen. Its description is the
    // help text; "Pointing at" lists both acts, the one with the suggestion and the reason
    // beside it, and the choice that sends the pose to another player to endorse.
    const editor = page.getByRole('textbox');
    await editor.fill(POSE_TEXT);
    const reach = page.getByTestId('reach-row');
    await reach.getByTestId('reach-toggle').click();
    await reach.getByTestId('reach-select').selectOption({ label: 'Cruelty' });
    await expect(reach.getByTestId('reach-help')).toHaveText(seed.cruelty_description);
    const acts = reach.getByTestId('reach-acts');
    await expect(acts.getByText('Pointing at', { exact: true })).toBeVisible();
    await expect(acts).toContainText('Intimidated Hale');
    await expect(acts).toContainText('Suggested: Cruelty. You left Hale in the grip of Terror.');
    await expect(acts).toContainText('Searched the cellar');
    await expect(acts).toContainText('No resonance suggested.');
    await expect(reach.getByTestId('reach-act-none')).toBeVisible();
    await expect(acts).toContainText('Nothing: another player has to endorse it');
    await reach.scrollIntoViewIfNeeded();
    await shot(testInfo, '02-composer-reaching-for-open.png', page);

    // Screen 3: point at Intimidated Hale and post. The room reads the chip, which names the
    // resonance and the act; Daven alone reads his private line, with the verb, the amount and
    // the check that grew it.
    await reach.getByTestId(`reach-act-${seed.act_intimidated_id}`).check();
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    const posed = poseWith(page, 'lantern light');
    await expect(posed).toBeVisible({ timeout: 30000 });
    await expect(posed.getByTestId('act-mark-chips')).toContainText('Cruelty · Intimidated Hale', {
      timeout: 30000,
    });
    const line = page
      .locator('[data-testid="feed-note"][data-kind="system"]')
      .filter({ hasText: 'Your Cruelty grows by' });
    await expect(line).toBeVisible({ timeout: 30000 });
    await expect(line).toContainText(/You gloat\. Your Cruelty grows by \d+\./);
    await expect(line).toContainText('Your Villainy check added 30 percent.');
    await posed.scrollIntoViewIfNeeded();
    await shot(testInfo, '03a-pose-with-chip.png', posed);
    await shot(testInfo, '03b-daven-private-line.png', line);
    await shot(testInfo, '03c-feed-with-chip-and-line.png', page);

    await page.context().close();
  });

  test('screens 3 and 7: Ilsa reads the same pose with a chip and no amount, and picks a resonance on Brannoc’s pose', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.witness_username, seed.player_password);
    await openScene(page, seed);

    // What the room reads: the resonance and the act, and never a number. Ilsa is a scene
    // co-owner and not its GM, so she is offered no Undo on the marked poses.
    const posed = poseWith(page, 'lantern light');
    await expect(posed).toBeVisible({ timeout: 30000 });
    const chips = posed.getByTestId('act-mark-chips');
    await expect(chips).toHaveText('Cruelty · Intimidated Hale');
    await expect(posed).not.toContainText(/grows by|percent|\b9\b/);
    await expect(page.getByRole('button', { name: 'Undo reward' })).toHaveCount(0);
    await posed.scrollIntoViewIfNeeded();
    await shot(testInfo, '03d-ilsa-reads-the-chip-no-amount.png', posed);

    // Screen 7: the Endorse menu on a pose that named no resonance lists every resonance under
    // its affinity, with nothing about Brannoc's aura.
    const bell = poseWith(page, 'cracked bell');
    const control = bell.getByTestId('endorsement-control-pose');
    await control.getByRole('button', { name: 'Endorse', exact: true }).click();
    const menu = page.getByRole('menu');
    await expect(menu).toBeVisible();
    for (const affinity of ['Primal', 'Celestial', 'Abyssal']) {
      await expect(menu.getByText(affinity, { exact: true })).toBeVisible();
    }
    for (const resonance of ['Fury', 'Grief', 'Mercy', 'Valor', 'Cruelty', 'Dread']) {
      await expect(menu.getByRole('menuitem', { name: resonance, exact: true })).toBeVisible();
    }
    await shot(testInfo, '07a-endorse-menu-every-resonance.png', page);

    // She picks Grief: the pick waits, with Change and Withdraw.
    await menu.getByRole('menuitem', { name: 'Grief', exact: true }).click();
    const waiting = control.getByTestId('pose-pick-waiting');
    await expect(waiting).toHaveText('Grief · waiting for Brannoc');
    await expect(control.getByRole('button', { name: 'Change', exact: true })).toBeVisible();
    await expect(control.getByRole('button', { name: 'Withdraw', exact: true })).toBeVisible();
    await bell.scrollIntoViewIfNeeded();
    await shot(testInfo, '07b-ilsa-pick-waiting.png', bell);

    // She meant Mercy: Change opens the same menu again.
    await control.getByRole('button', { name: 'Change', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Mercy', exact: true }).click();
    await expect(waiting).toHaveText('Mercy · waiting for Brannoc');
    await shot(testInfo, '07c-ilsa-pick-changed.png', bell);

    await page.context().close();
  });

  test('screen 7: Brannoc reads the proposal with Accept and Decline', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(120_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.bell_poser_username, seed.player_password);
    await openScene(page, seed);

    const bell = poseWith(page, 'cracked bell');
    const proposal = bell.locator('[data-testid^="pose-pick-proposal-"]');
    await expect(proposal).toBeVisible({ timeout: 30000 });
    await expect(proposal).toContainText('Ilsa proposed Mercy');
    await expect(proposal.getByRole('button', { name: 'Accept', exact: true })).toBeVisible();
    await expect(proposal.getByRole('button', { name: 'Decline', exact: true })).toBeVisible();
    // The poser has no Endorse menu on her own pose.
    await expect(bell.getByRole('button', { name: 'Endorse', exact: true })).toHaveCount(0);
    await bell.scrollIntoViewIfNeeded();
    await shot(testInfo, '07d-brannoc-reads-the-proposal.png', bell);

    await page.context().close();
  });

  test('screen 8: the scene’s GM undoes a reward and opens the tag dialog with its resonance picker', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.gm_username, seed.gm_password);
    await openScene(page, seed);

    // A marked pose offers the GM "Undo reward".
    const marked = poseWith(page, 'catches the child');
    const chip = marked.getByTestId(`act-mark-${seed.marked_grant_id}`);
    await expect(chip).toHaveText('Mercy · Frightened the child', { timeout: 30000 });
    const undo = marked.getByTestId(`undo-reward-${seed.marked_grant_id}`);
    await expect(undo).toBeVisible();
    await marked.scrollIntoViewIfNeeded();
    await shot(testInfo, '08a-gm-sees-undo-reward.png', marked);

    // After the undo the chip is struck through and names the role that undid it.
    await undo.click();
    await expect(marked.getByTestId('act-mark-undone')).toHaveText(
      "Reward undone by the scene's GM",
      { timeout: 30000 }
    );
    await expect(undo).toHaveCount(0);
    await shot(testInfo, '08b-reward-undone.png', marked);

    // The tag dialog: the moment type and the resonance picker, which lists every resonance.
    await marked.getByTestId('tag-moment-button').click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText('Tag Dramatic Moment', { exact: true })).toBeVisible();
    await dialog.getByTestId('moment-type-select').click();
    await page.getByRole('option', { name: seed.moment_type_label, exact: true }).click();
    const picker = dialog.getByTestId('moment-resonance-select');
    await expect(picker).toBeVisible({ timeout: 30000 });
    await picker.click();
    for (const resonance of ['Fury', 'Grief', 'Mercy', 'Valor', 'Cruelty', 'Dread']) {
      await expect(page.getByRole('option', { name: resonance, exact: true })).toBeVisible();
    }
    await page.getByRole('option', { name: 'Grief', exact: true }).click();
    await expect(picker).toContainText('Grief');
    await shot(testInfo, '08c-tag-dialog-resonance-picker.png', dialog);
    // Nothing is tagged: the dialog is closed with Cancel.
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).toHaveCount(0);

    await page.context().close();
  });

  test('screen 10: the admin pages that set the numbers and text the screens read', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.staff_username, seed.staff_password);

    // The Abyssal affinity: its verb and its gain fatigue.
    await page.goto(`/admin/arxii/affinity/${seed.abyssal_affinity_id}/change/`);
    await expect(page.locator('#id_claim_verb')).toHaveValue('gloat');
    await expect(page.locator('#id_gain_fatigue')).toHaveValue('6');
    await expect(page.locator('.field-claim_verb label')).toHaveText(/Claim verb/);
    await expect(page.locator('.field-gain_fatigue label')).toHaveText(/Gain fatigue/);
    await page.locator('.field-claim_verb').scrollIntoViewIfNeeded();
    await shot(testInfo, '10a-affinity-claim-verb-gain-fatigue.png', page, { fullPage: true });

    // The weekly table: one row for each step.
    await page.goto('/admin/arxii/weeklymarkreturn/');
    await expect(page.locator('#result_list tbody tr')).toHaveCount(seed.weekly_row_count);
    await shot(testInfo, '10b-weekly-mark-returns.png', page, { fullPage: true });

    // The kindling settings: how many days an act stays on her list.
    await page.goto('/admin/arxii/kindlingconfig/');
    await expect(page.locator('#id_recorded_act_days')).toHaveValue('90');
    await page.locator('.field-recorded_act_days').scrollIntoViewIfNeeded();
    await shot(testInfo, '10c-kindling-recorded-act-days.png', page, { fullPage: true });

    // A resonance's description, which is the picker's help text.
    await page.goto(`/admin/arxii/resonance/${seed.cruelty_id}/change/`);
    await expect(page.locator('#id_description')).toHaveValue(seed.cruelty_description);
    await shot(testInfo, '10d-resonance-description.png', page, { fullPage: true });

    // The stat a marked act's bonus check rolls when the act rolled none of its own.
    await page.goto(`/admin/arxii/resonancegainsourcestat/${seed.gain_source_stat_id}/change/`);
    await expect(page.locator('#id_source option:checked')).toHaveText('Marked act');
    await expect(page.locator('#id_stat option:checked')).toContainText('presence');
    await shot(testInfo, '10e-gain-source-stat-marked-act.png', page, { fullPage: true });

    await page.context().close();
  });
});
