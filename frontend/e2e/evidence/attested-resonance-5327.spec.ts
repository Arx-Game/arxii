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
 * Needs the rows `integration_tests.live_seeds.seed_attested_resonance_spec` writes (the
 * coordinator writes its result to the JSON file named by ATTESTED_RESONANCE_SEED, default
 * /tmp/attested-resonance-seed.json), and the seed run again before every run of this spec:
 * marking an act, undoing a reward and tagging a pose change what the next run starts from, and
 * the seed is what clears them.
 *
 * The main scene (The Lantern) holds Daven (e2e_test_account), Hale, Ilsa (a scene co-owner, not
 * its GM), Brannoc and Marek (the scene's GM). Each frame that needs another state has a cast of
 * its own with the same names, so it is taken from an untouched state: a Hale with 3 of
 * fatigue room (a shrunk gain), a Hale with none (a refused mark), a Daven who already made four
 * marks this week (the fifth pays 40 percent), Tamsin (a Primal mark that tires her), a Wren in
 * a road scene that stores nothing, and a Wren whose week of marks is spent.
 *
 * One named PNG per frame of the approved demo (.demos/issue-5327-attested-resonance.html), in
 * the demo's order, each written to the test's own output folder, which `just shot` lists when
 * the run ends. The tests are independent: one failing does not hide the others.
 *
 * Left out: Screen 9 (telnet, not a screen of the web app).
 */

const ACCOUNT = 'e2e_test_account';
const PASSWORD = 'TestPass123!';
const VIEWPORT = { width: 1440, height: 900 };
const SAY_IT_AGAIN = 'leans over Hale. "Say it again."';
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
  fury_description: string;
  weekly_row_count: number;
  kindling_config_id: number;
  gain_source_stat_id: number;
  player_password: string;
  hale_username: string;
  witness_username: string;
  bell_poser_username: string;
  gm_username: string;
  gm_password: string;
  staff_username: string;
  staff_password: string;
  shrunk_poser_username: string;
  shrunk_target_username: string;
  shrunk_act_id: number;
  refused_poser_username: string;
  refused_act_id: number;
  week_poser_username: string;
  week_act_id: number;
  tamsin_username: string;
  tamsin_act_id: number;
  wren_username: string;
  wren_tended_act_id: number;
  wren_fine_act_id: number;
  wren_refused_username: string;
  wren_refused_act_id: number;
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

/**
 * One PNG of the page cut to the box that holds all of `targets`, with a margin: a pose and the
 * private line under it, as the demo draws them, without the rest of the play page around them.
 */
async function shotAround(
  testInfo: TestInfo,
  name: string,
  page: Page,
  targets: Locator[],
  extraBottom = 0
) {
  const boxes = [];
  for (const target of targets) {
    await target.scrollIntoViewIfNeeded();
    const box = await target.boundingBox();
    if (box === null) throw new Error(`${name}: a target has no box to cut around`);
    boxes.push(box);
  }
  const margin = 6;
  const left = Math.max(0, Math.min(...boxes.map((box) => box.x)) - margin);
  const top = Math.max(0, Math.min(...boxes.map((box) => box.y)) - margin);
  const right = Math.max(...boxes.map((box) => box.x + box.width)) + margin;
  const bottom = Math.max(...boxes.map((box) => box.y + box.height)) + 1 + extraBottom;
  await page.screenshot({
    path: testInfo.outputPath(name),
    clip: { x: left, y: top, width: right - left, height: bottom - top },
  });
}

/** The pose in the feed whose text holds `text`. */
function poseWith(page: Page, text: string): Locator {
  return page.getByTestId('pose-unit').filter({ hasText: text });
}

/** Wait for every finite animation and transition under `target` to end, never a fixed sleep. */
async function settled(target: Locator) {
  await target.evaluate((element) =>
    Promise.all(
      element
        .getAnimations({ subtree: true })
        .filter((animation) => animation.effect?.getComputedTiming().iterations !== Infinity)
        .map((animation) => animation.finished)
    )
  );
}

/** The play page, entered as the account's only character (`name`), with the composer ready. */
async function enterGame(page: Page, name: string) {
  await page.goto('/game');
  await page
    .locator(
      `button[title="Connect as ${name}"], button[title="Switch to ${name}"], ` +
        `button[title="${name}"], button:has-text("${name}")`
    )
    .first()
    .click({ timeout: 30000 });
  await expect(page.getByTestId('reach-row')).toBeVisible({ timeout: 60000 });
}

/** Point a pose at an act with a resonance and send it from the composer. */
async function markAndSend(
  page: Page,
  options: { text: string; resonance: string; actId: number }
) {
  await page.getByRole('textbox').fill(options.text);
  const reach = page.getByTestId('reach-row');
  await reach.getByTestId('reach-toggle').click();
  await reach.getByTestId('reach-select').selectOption({ label: options.resonance });
  await reach.getByTestId(`reach-act-${options.actId}`).check();
  await page.getByRole('button', { name: 'Send', exact: true }).click();
}

/** A toast (a line the player reads once) holding `text`. */
function toastWith(page: Page, text: string | RegExp): Locator {
  return page.locator('[data-sonner-toast]').filter({ hasText: text });
}

/** A private line in the play feed (a stored line is delivered when the player connects). */
function feedLine(page: Page, text: string | RegExp): Locator {
  return page.getByText(text).first();
}

/** The scene page, once its feed has loaded the pose Brannoc wrote. */
async function openScene(page: Page, seed: Seed) {
  await page.goto(`/scenes/${seed.scene_id}`);
  await expect(poseWith(page, 'cracked bell')).toBeVisible({ timeout: 45000 });
}

test.use({ viewport: VIEWPORT });

test.describe('A character gains resonance from the acts she took (#5327)', () => {
  test('01 to 03 screens 1 to 3: the composer, the result, and the mission beat she then picks', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(240_000);
    const seed = readSeed();
    const page = await signedInPage(browser, ACCOUNT, PASSWORD);
    await enterGame(page, seed.daven_name);
    // Daven's session stays open to the end: a mission pauses the moment its player disconnects,
    // so the mission frames come last, after the composer frames, in the same session. A failure
    // in one part does not hide the other.
    const failures: unknown[] = [];
    try {
      // The scene's feed is loaded once Brannoc's pose is in it.
      await expect(poseWith(page, 'cracked bell')).toBeVisible({ timeout: 60000 });

      // Screen 2: the composer's Reaching for row, with Cruelty chosen. Its description is the
      // help text; "Pointing at" lists both acts, the one with the suggestion and the reason
      // beside it, and the choice that sends the pose to another player to endorse.
      await page.getByRole('textbox').fill(POSE_TEXT);
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
      await shot(testInfo, '02a-composer-reaching-for-open.png', page);

      // She chooses Intimidated Hale: the demo draws the act chosen.
      await reach.getByTestId(`reach-act-${seed.act_intimidated_id}`).check();
      await expect(reach.getByTestId(`reach-act-${seed.act_intimidated_id}`)).toBeChecked();
      await shot(testInfo, '02b-composer-act-chosen.png', page);

      // Screen 3: post. The room reads the chip, which names the resonance and the act; Daven
      // alone reads his private line, with the verb, the amount and the check that grew it.
      await page.getByRole('button', { name: 'Send', exact: true }).click();
      const posed = poseWith(page, 'lantern light');
      await expect(posed).toBeVisible({ timeout: 30000 });
      await expect(posed.getByTestId('act-mark-chips')).toContainText(
        'Cruelty · Intimidated Hale',
        {
          timeout: 30000,
        }
      );
      const line = page
        .locator('[data-testid="feed-note"][data-kind="system"]')
        .filter({ hasText: 'Your Cruelty grows by' });
      await expect(line).toBeVisible({ timeout: 30000 });
      await expect(line).toContainText(/You gloat\. Your Cruelty grows by \d+\./);
      await expect(line).toContainText('Your Villainy check added 30 percent.');
      await posed.scrollIntoViewIfNeeded();
      await shot(testInfo, '03a-pose-with-chip.png', posed);
      await shot(testInfo, '03b-daven-private-line.png', line);
      await shotAround(testInfo, '03c-feed-with-chip-and-line.png', page, [posed, line]);
    } catch (error) {
      failures.push(error);
    }
    try {
      // Before she picks: the option that names Mercy says what it pays, with the mission theme's
      // player text as the reason, and shows no amount; the other option says nothing of the kind.
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
      await shot(testInfo, '01a-mission-beat-option-pays-mercy.png', row);

      // She picks it. Her staff roll modifier is +100, so the roll lands on the best result its
      // chart has, and the authored choice pays.
      await beat
        .getByTestId('beat-option')
        .first()
        .getByRole('button', { name: /Let the smugglers go/ })
        .click();
      await expect(row.getByTestId('beat-result')).toBeVisible({ timeout: 30000 });
      const earned = feedLine(page, /You earned \d+ Mercy\./);
      await expect(earned).toBeVisible({ timeout: 30000 });
      await expect(earned).toContainText('Your Heroism check added 30 percent.');
      // The next line of the feed is what the pick did in the story.
      await shotAround(testInfo, '01b-earned-line-after-the-pick.png', page, [earned], 46);
      await shot(testInfo, '01c-beat-result-after-the-pick.png', row.getByTestId('beat-result'));
    } catch (error) {
      failures.push(error);
    }
    await page.context().close();
    if (failures.length > 0) throw failures[0];
  });

  test('02 screen 2: in a scene that stores nothing, the row warns that a mark pays nothing', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.wren_username, seed.player_password);
    await enterGame(page, 'Wren');
    await page
      .getByRole('textbox')
      .fill("kneels in the road and presses a cloth to the stranger's side.");
    const reach = page.getByTestId('reach-row');
    await reach.getByTestId('reach-toggle').click();
    await reach.getByTestId('reach-select').selectOption({ label: 'Mercy' });
    await expect(reach.getByTestId('reach-help')).toHaveText(seed.mercy_description);
    const warning = reach.getByTestId('reach-ephemeral');
    await expect(warning).toContainText(
      'This scene is ephemeral and stores nothing, so a mark here pays nothing.'
    );
    // No act list: it gives way to the warning.
    await expect(reach.getByTestId('reach-acts')).toHaveCount(0);
    await reach.scrollIntoViewIfNeeded();
    await shot(testInfo, '02c-ephemeral-scene-warning.png', page);

    await page.context().close();
  });

  test('03 screen 3: Ilsa reads the same pose with a chip and no amount', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(120_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.witness_username, seed.player_password);
    await openScene(page, seed);

    // What the room reads: the resonance and the act, and never a number. Ilsa is a scene
    // co-owner and not its GM, so she is offered no Undo on the marked poses.
    const posed = poseWith(page, 'lantern light');
    await expect(posed).toBeVisible({ timeout: 30000 });
    await expect(posed.getByTestId('act-mark-chips')).toHaveText('Cruelty · Intimidated Hale');
    await expect(posed).not.toContainText(/grows by|percent|\b9\b/);
    await expect(page.getByRole('button', { name: 'Undo reward' })).toHaveCount(0);
    await posed.scrollIntoViewIfNeeded();
    await shot(testInfo, '03d-ilsa-reads-the-chip-no-amount.png', posed);

    await page.context().close();
  });

  test('04 screen 4: Hale reads that he is wearier', async ({ browser }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.hale_username, seed.player_password);
    await enterGame(page, 'Hale');
    const posed = poseWith(page, 'lantern light');
    await expect(posed.getByTestId('act-mark-chips')).toContainText('Cruelty · Intimidated Hale', {
      timeout: 60000,
    });
    const line = feedLine(page, 'Daven marked Cruelty on what they did to you. You are wearier.');
    await expect(line).toBeVisible({ timeout: 30000 });
    await shotAround(testInfo, '04a-hale-reads-wearier.png', page, [posed, line]);

    await page.context().close();
  });

  test('04 screen 4: a target with little left pays part, and both are told why', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(240_000);
    const seed = readSeed();
    const daven = await signedInPage(browser, seed.shrunk_poser_username, seed.player_password);
    await enterGame(daven, seed.daven_name);
    await markAndSend(daven, {
      text: SAY_IT_AGAIN,
      resonance: 'Cruelty',
      actId: seed.shrunk_act_id,
    });
    const mark = feedLine(
      daven,
      /You gloat\. Your Cruelty grows by \d+ instead of \d+, because Hale had little left to give\./
    );
    await expect(mark).toBeVisible({ timeout: 30000 });
    await expect(mark).toContainText('Marks against Hale stay small until they have recovered.');
    await expect(poseWith(daven, 'Say it again').getByTestId('act-mark-chips')).toContainText(
      'Cruelty · Intimidated Hale',
      { timeout: 30000 }
    );
    await shotAround(testInfo, '04c-daven-reads-part-paid.png', daven, [
      poseWith(daven, 'Say it again'),
      mark,
    ]);
    await daven.context().close();

    // What Hale reads, with the same pose on his page.
    const hale = await signedInPage(browser, seed.shrunk_target_username, seed.player_password);
    await enterGame(hale, 'Hale');
    await expect(poseWith(hale, 'Say it again').getByTestId('act-mark-chips')).toContainText(
      'Cruelty · Intimidated Hale',
      { timeout: 60000 }
    );
    const line = feedLine(
      hale,
      'Daven marked Cruelty on what they did to you. You are wearier. You had little left to give, so it took only part.'
    );
    await expect(line).toBeVisible({ timeout: 30000 });
    await shotAround(testInfo, '04b-hale-reads-took-only-part.png', hale, [
      poseWith(hale, 'Say it again'),
      line,
    ]);
    await hale.context().close();
  });

  test('04 screen 4: a target with nothing left refuses the mark, and the act stays on the list', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(240_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.refused_poser_username, seed.player_password);
    await enterGame(page, seed.daven_name);
    await markAndSend(page, {
      text: SAY_IT_AGAIN,
      resonance: 'Cruelty',
      actId: seed.refused_act_id,
    });
    // The refusal is shown as an error, in the words the demo draws.
    const refusal = toastWith(page, 'Hale is too worn to pay for this');
    await expect(refusal).toContainText(
      'Hale is too worn to pay for this, so your Cruelty does not grow. The act stays on your list. Mark it again once Hale has recovered, or mark another act.',
      { timeout: 30000 }
    );
    await settled(refusal);
    // The pose still posted, with no chip, and nothing was paid.
    const posed = poseWith(page, 'Say it again');
    await expect(posed).toBeVisible({ timeout: 30000 });
    await expect(posed.getByTestId('act-mark-chips')).toHaveCount(0);
    await shot(testInfo, '04d-daven-reads-refusal.png', page);

    // The act is still on his list.
    await expect(refusal).toHaveCount(0, { timeout: 30000 });
    const reach = page.getByTestId('reach-row');
    await reach.getByTestId('reach-toggle').click();
    await reach.getByTestId('reach-select').selectOption({ label: 'Cruelty' });
    await expect(reach.getByTestId(`reach-act-${seed.refused_act_id}`)).toBeVisible();
    await expect(reach.getByTestId('reach-acts')).toContainText('Intimidated Hale');
    await reach.scrollIntoViewIfNeeded();
    await shot(testInfo, '04e-act-still-on-the-list.png', page);

    await page.context().close();
  });

  test('04 screen 4: a later mark in the week pays the table’s reduced percent', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(240_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.week_poser_username, seed.player_password);
    await enterGame(page, seed.daven_name);
    await markAndSend(page, {
      text: SAY_IT_AGAIN,
      resonance: 'Cruelty',
      actId: seed.week_act_id,
    });
    const mark = feedLine(page, /You gloat\. Your Cruelty grows by \d+\. This is your fifth mark/);
    await expect(mark).toBeVisible({ timeout: 30000 });
    await expect(mark).toContainText(
      'This is your fifth mark this week, so it paid 40 percent. Marks pay in full again next week.'
    );
    await shotAround(testInfo, '04f-daven-reads-fifth-mark-reduced.png', page, [
      poseWith(page, 'Say it again'),
      mark,
    ]);

    await page.context().close();
  });

  test('05 screen 5: a Primal mark, where she herself is wearier', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(240_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.tamsin_username, seed.player_password);
    await enterGame(page, 'Tamsin');
    const text =
      'drives her shoulder into the raider and swings, with three of them closing the gap behind her.';
    await page.getByRole('textbox').fill(text);
    const reach = page.getByTestId('reach-row');
    await reach.getByTestId('reach-toggle').click();
    await reach.getByTestId('reach-select').selectOption({ label: 'Fury' });
    await expect(reach.getByTestId('reach-help')).toHaveText(seed.fury_description);
    const acts = reach.getByTestId('reach-acts');
    await expect(acts).toContainText('Struck the raider');
    await expect(acts).toContainText('Suggested: Fury. You are surrounded.');
    await expect(reach.getByTestId('reach-act-none')).toBeVisible();
    await reach.scrollIntoViewIfNeeded();
    await shot(testInfo, '05a-composer-fury-struck-the-raider.png', page);

    await reach.getByTestId(`reach-act-${seed.tamsin_act_id}`).check();
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    const posed = poseWith(page, 'closing the gap behind her');
    await expect(posed.getByTestId('act-mark-chips')).toContainText('Fury · Struck the raider', {
      timeout: 30000,
    });
    const line = feedLine(page, /You blaze\. Your Fury grows by \d+, and you are wearier\./);
    await expect(line).toBeVisible({ timeout: 30000 });
    await expect(line).toContainText('Your Reflection check added 30 percent.');
    await shotAround(testInfo, '05b-tamsin-reads-blaze-wearier.png', page, [posed, line]);

    await page.context().close();
  });

  test('06 screen 6: Wren’s journal form, and the line she reads after she posts', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.wren_username, seed.player_password);
    await page.goto('/journals');
    await page.getByRole('button', { name: 'Write', exact: true }).click();
    const desk = page.locator('section[aria-label="Write in your journal"]');
    await expect(desk).toBeVisible({ timeout: 30000 });
    await desk.getByLabel('Title', { exact: true }).fill('The stranger at the tollgate');
    await desk
      .getByLabel('Entry', { exact: true })
      .fill(
        'I should have stopped sooner. I did not know his name, only that he was bleeding on the road and nobody else would kneel.'
      );
    await desk.getByTestId('reach-toggle').click();
    await desk.getByTestId('reach-select').selectOption({ label: 'Mercy' });
    await expect(desk.getByTestId('reach-help')).toHaveText(seed.mercy_description);
    const acts = desk.getByTestId('reach-acts');
    await expect(acts.getByText('Pointing at (required)', { exact: true })).toBeVisible();
    await expect(acts).toContainText('Tended the stranger');
    await expect(acts).toContainText('Suggested: Mercy. Someone here is in trouble.');
    await expect(acts).toContainText('Paid the tollgate fine');
    await expect(acts).toContainText('No resonance suggested.');
    // A journal entry has no "Nothing" choice: no one can endorse a journal entry.
    await expect(desk.getByTestId('reach-act-none')).toHaveCount(0);
    // With no act chosen the entry cannot be posted.
    await expect(desk.getByRole('button', { name: 'Post entry' })).toBeDisabled();
    await desk.scrollIntoViewIfNeeded();
    await shot(testInfo, '06a-journal-form-act-required.png', desk);

    // She chooses the act and posts: the line she reads.
    await desk.getByTestId(`reach-act-${seed.wren_tended_act_id}`).check();
    await desk.getByRole('button', { name: 'Post entry' }).click();
    const line = toastWith(page, /You inspire\. Your Mercy grows by \d+/);
    await expect(line).toBeVisible({ timeout: 30000 });
    await expect(line).toContainText(', and you are wearier. Your Heroism check added 30 percent.');
    await settled(line);
    await shot(testInfo, '06b-wren-reads-inspire-wearier.png', page);

    await page.context().close();
  });

  test('06 screen 6: a refused journal mark leaves the entry posted and shows the refusal as an error', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.wren_refused_username, seed.player_password);
    await page.goto('/journals');
    await page.getByRole('button', { name: 'Write', exact: true }).click();
    const desk = page.locator('section[aria-label="Write in your journal"]');
    await expect(desk).toBeVisible({ timeout: 30000 });
    await desk.getByLabel('Title', { exact: true }).fill('The tollgate, a second time');
    await desk
      .getByLabel('Entry', { exact: true })
      .fill('I went back to the road and found it empty. I wrote down what I could.');
    await desk.getByTestId('reach-toggle').click();
    await desk.getByTestId('reach-select').selectOption({ label: 'Mercy' });
    await desk.getByTestId(`reach-act-${seed.wren_refused_act_id}`).check();
    await desk.getByRole('button', { name: 'Post entry' }).click();
    const refusal = toastWith(page, 'have already paid all they will');
    await expect(refusal).toContainText(
      'Your marks this week have already paid all they will, so this one would pay nothing. The act stays on your list: mark it next week, when marks pay in full again.',
      { timeout: 30000 }
    );
    // The entry itself was recorded.
    await expect(toastWith(page, 'Journal entry recorded.')).toBeVisible();
    // Hovering a toast opens the stack, so both lines read in full.
    await refusal.hover();
    await settled(refusal);
    await expect(page.getByText('The tollgate, a second time').first()).toBeVisible();
    await shot(testInfo, '06c-journal-mark-refused-entry-posted.png', page);

    await page.context().close();
  });

  test('07 screen 7: Ilsa picks a resonance on Brannoc’s pose, and changes it', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.witness_username, seed.player_password);
    await openScene(page, seed);

    // The Endorse menu on a pose that named no resonance lists every resonance under its
    // affinity, with nothing about Brannoc's aura.
    const bell = poseWith(page, 'cracked bell');
    const control = bell.getByTestId('endorsement-control-pose');
    await control.getByRole('button', { name: 'Endorse', exact: true }).click();
    const menu = page.getByRole('menu');
    await expect(menu).toBeVisible();
    for (const affinity of ['Abyssal', 'Celestial', 'Primal']) {
      await expect(menu.getByText(affinity, { exact: true })).toBeVisible();
    }
    for (const resonance of ['Cruelty', 'Dread', 'Mercy', 'Valor', 'Fury', 'Grief']) {
      await expect(menu.getByRole('menuitem', { name: resonance, exact: true })).toBeVisible();
    }
    // The menu fades in; wait for that to finish so the feed does not show through it.
    await settled(menu);
    await expect(menu).toHaveCSS('opacity', '1');
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

  test('07 screen 7: Brannoc reads the proposal with Accept and Decline', async ({
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

  test('08 screen 8: the scene’s GM undoes a reward, tags a pose with a resonance, and the tag dialog', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(240_000);
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
    for (const resonance of ['Cruelty', 'Dread', 'Mercy', 'Valor', 'Fury', 'Grief']) {
      await expect(page.getByRole('option', { name: resonance, exact: true })).toBeVisible();
    }
    await page.getByRole('option', { name: 'Grief', exact: true }).click();
    await expect(picker).toContainText('Grief');
    await shot(testInfo, '08c-tag-dialog-resonance-picker.png', dialog);

    // She tags it: the pose carries the tag.
    await dialog.getByTestId('tag-moment-submit').click();
    await expect(dialog).toHaveCount(0, { timeout: 30000 });
    await expect(marked.getByTestId('dramatic-moment-badges')).toContainText(
      seed.moment_type_label,
      { timeout: 30000 }
    );
    await marked.scrollIntoViewIfNeeded();
    await shot(testInfo, '08d-pose-tagged.png', marked);

    await page.context().close();
  });

  test('08 screen 8: Daven reads the lines the GM’s tag and undo sent him', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(240_000);
    const seed = readSeed();
    const page = await signedInPage(browser, ACCOUNT, PASSWORD);
    await enterGame(page, seed.daven_name);
    const tagLine = feedLine(
      page,
      `The scene's GM tagged your pose: ${seed.moment_type_label}. It paid you Grief.`
    );
    await expect(tagLine).toBeVisible({ timeout: 60000 });
    await shotAround(testInfo, '08e-daven-reads-the-tag-line.png', page, [
      poseWith(page, 'catches the child'),
      tagLine,
    ]);
    const undoLine = feedLine(
      page,
      "The scene's GM undid your Mercy reward for Frightened the child. Your Mercy falls by 8."
    );
    await expect(undoLine).toBeVisible({ timeout: 30000 });
    await shotAround(testInfo, '08f-daven-reads-the-undo-line.png', page, [
      poseWith(page, 'catches the child'),
      undoLine,
    ]);

    await page.context().close();
  });

  test('10 screen 10: the admin pages that set the numbers and text the screens read', async ({
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

    // The weekly table: one page of rows edited in place.
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
