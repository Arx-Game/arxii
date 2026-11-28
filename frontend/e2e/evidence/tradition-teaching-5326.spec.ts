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
 * Review evidence for #5326, against a live server (no mocked /api/**), run by
 * `just shot --spec e2e/evidence/tradition-teaching-5326.spec.ts` on the `rt_5326` database.
 *
 * Needs the rows `integration_tests.live_seeds.seed_tradition_teaching_spec` writes for
 * e2e_test_account (the coordinator writes its result to the JSON file named by
 * TRADITION_TEACHING_SEED): Heroism, Reflection and Villainy linked to their affinities; the
 * Lantern Concord (teaches Heroism) and the Cinder Court (teaches Villainy); an other-Tradition
 * course difficulty of 3; the self-teaching target and a distinction carrying one effect on it;
 * two Academy master roles with a Villainy course each; Wren Alder (Lantern Concord, 6 action
 * points, 3 of them already asked of Drusa Kell) standing in the Cinder Hall with the Cinder
 * Court master; mentors; a creation draft at the Gift stage with the Lantern Concord chosen; a
 * staff account for admin; a mentor account that plays Drusa Kell and Aldric Voss; and a game
 * master account that holds two NPCs (Magister Vey and Warden Ilsa Tarn).
 *
 * One named PNG per screen of the approved demo (.demos/issue-5326-traditions-teach.html), each
 * written to the test's own output folder, which `just shot` lists when the run ends. The
 * mentor's and the game master's answers (Accept, Decline) change rows for good, so run the seed
 * again before a second run of this spec. The rest changes nothing a second run would trip over:
 * the allocation the student saves is removed again, and the Skill Course Offer Details page
 * saved in screen 5 is saved with the values it already had.
 */

const ACCOUNT = 'e2e_test_account';
const PASSWORD = 'TestPass123!';
const VIEWPORT = { width: 1440, height: 900 };

interface Seed {
  good_tradition_id: number;
  good_tradition_name: string;
  evil_tradition_id: number;
  evil_tradition_name: string;
  config_id: number;
  modifier_target_id: number;
  distinction_id: number;
  evil_role_id: number;
  evil_course_id: number;
  trainer_role_id: number;
  lantern_course_id: number;
  bare_course_id: number;
  trainer_name: string;
  entry_id: number;
  character_id: number;
  character_name: string;
  draft_id: number;
  mentor_good: string;
  mentor_unrated: string;
  mentor_rated: string;
  staff_username: string;
  staff_password: string;
  own_alt_name: string;
  mentor_username: string;
  mentor_password: string;
  mentor_entry_id: number;
  gm_username: string;
  gm_password: string;
  gm_entry_id: number;
  gm_character_name: string;
  npc_cannot_teach: string;
  npc_declined: string;
  student_of_aldric: string;
  student_taught: string;
  student_of_vey: string;
  student_of_ilsa: string;
  cinder_username: string;
  cinder_password: string;
  cinder_character_name: string;
  wren_allocation_id: number;
  aldric_allocation_id: number;
  taught_allocation_id: number;
  vey_allocation_id: number;
  ilsa_allocation_id: number;
}

function readSeed(): Seed {
  return JSON.parse(
    readFileSync(process.env.TRADITION_TEACHING_SEED ?? '/tmp/tradition-teaching-seed.json', 'utf8')
  ) as Seed;
}

async function logIn(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill(username);
  await page.getByPlaceholder('Password').fill(password);
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

async function signedInPage(browser: Browser, username: string, password: string): Promise<Page> {
  const context = await browser.newContext({ viewport: VIEWPORT });
  const page = await context.newPage();
  await logIn(page, username, password);
  return page;
}

/** Opens the Growth section of the character sheet at `/characters/<entry id>`. */
async function openGrowth(page: Page, entryId: number) {
  await page.goto(`/characters/${entryId}`);
  await page
    .getByRole('navigation', { name: 'Character sheet sections' })
    .getByRole('button', { name: 'Growth', exact: true })
    .click();
}

/**
 * The toast carrying `line`, once it is on screen and has finished sliding and fading in, so a
 * picture of it is not a frame from the middle of the animation.
 */
async function toastShown(page: Page, line: string): Promise<Locator> {
  const toast = page.locator('[data-sonner-toast]', { hasText: line });
  await expect(toast).toBeVisible();
  await toast.evaluate(async (el) => {
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    await Promise.all(el.getAnimations({ subtree: true }).map((a) => a.finished));
  });
  return toast;
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

/** A native disclosure (`details.entry`), opened by its own summary when it is closed. */
async function openEntry(entry: Locator) {
  const details = entry.locator('details.entry').first();
  const isOpen = await details.evaluate((el) => (el as HTMLDetailsElement).open);
  if (!isOpen) await details.locator('summary').first().click();
  await expect(details).toHaveAttribute('open', '');
}

test.describe.configure({ mode: 'serial' });
test.use({ viewport: VIEWPORT });

test.describe('Traditions decide what their teachers teach (#5326)', () => {
  test('screens 1 to 5: staff choose the taught skills, set the difficulty, author the lever, name the trainer Tradition and meet the refusal', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.staff_username, seed.staff_password);

    // Screen 1: the Tradition page, scrolled to "Taught skills". The chooser offers
    // Villainy and holds Heroism; Reflection is taught by every Tradition and is not listed.
    await page.goto(`/admin/arxii/tradition/${seed.good_tradition_id}/change/`);
    await expect(page.locator('#id_taught_skills_to option')).toHaveText(['Heroism']);
    await expect(page.locator('#id_taught_skills_from option')).toHaveText(['Villainy']);
    await expect(page.locator('option', { hasText: 'Reflection' })).toHaveCount(0);
    await page.locator('.field-taught_skills').scrollIntoViewIfNeeded();
    await shot(testInfo, '01-tradition-taught-skills.png', page, { fullPage: true });

    // Screen 2: the teaching settings page with the new number.
    await page.goto(`/admin/arxii/traditionteachingconfig/${seed.config_id}/change/`);
    await expect(page.locator('#id_other_tradition_course_difficulty')).toHaveValue('3');
    await shot(testInfo, '02-teaching-config-difficulty.png', page, { fullPage: true });

    // Screen 3: the modifier target, then the distinction's effect on it in the builder.
    // The Add page as staff meet it, with the three values typed in and nothing saved.
    await page.goto('/admin/arxii/modifiertarget/add/');
    await page.locator('#id_name').fill('self_teaching');
    const category = await page
      .locator('#id_category option', { hasText: 'self_teaching' })
      .first()
      .getAttribute('value');
    if (category) await page.locator('#id_category').selectOption(category);
    await page
      .locator('#id_description')
      .fill(
        'Teaching herself magic: a positive total lets the character allocate weekly ' +
          'training on a Magic skill with no mentor. Yes or no; a larger value adds nothing.'
      );
    await shot(testInfo, '03a-modifier-target-add-form.png', page, { fullPage: true });
    // The row staff saved, as the game reads it.
    await page.goto(`/admin/arxii/modifiertarget/${seed.modifier_target_id}/change/`);
    await expect(page.locator('#id_name')).toHaveValue('self_teaching');
    await shot(testInfo, '03b-modifier-target-saved.png', page, { fullPage: true });
    await page.goto(`/admin/_distinction_builder/${seed.distinction_id}/`);
    await expect(page.getByRole('heading', { name: 'Distinction Builder' })).toBeVisible();
    await expect(page.locator('#effects-body')).toContainText(/self_teaching/);
    await page.locator('#effects-module').scrollIntoViewIfNeeded();
    await shot(testInfo, '03c-distinction-builder-effect.png', page, { fullPage: true });

    // Screen 4: the trainer role's page, naming the Tradition it teaches.
    await page.goto(`/admin/arxii/npcrole/${seed.evil_role_id}/change/`);
    await expect(page.locator('#id_teaches_tradition')).toHaveValue(String(seed.evil_tradition_id));
    await page.locator('.field-teaches_tradition').scrollIntoViewIfNeeded();
    await shot(testInfo, '04-npc-role-teaches-tradition.png', page, { fullPage: true });

    // Screen 5, first frame: the Cinder Court teaches Villainy, so the course saves. It is
    // saved with the values it already holds.
    await page.goto(`/admin/arxii/skillcourseofferdetails/${seed.evil_course_id}/change/`);
    await expect(
      page.locator('div.readonly', { hasText: `Academy master of ${seed.evil_tradition_name}` })
    ).toBeVisible();
    await shot(testInfo, '05a-course-offer-before-save.png', page, { fullPage: true });
    await page.locator('input[name="_continue"]').click();
    await expect(page.locator('.messagelist .success')).toBeVisible();
    await shot(testInfo, '05b-course-offer-saved.png', page, { fullPage: true });

    // Screen 5, second frame: a Villainy course on a role of the Lantern Concord, which does
    // not teach Villainy. The save is refused and nothing changes.
    await page.goto(`/admin/arxii/skillcourseofferdetails/${seed.lantern_course_id}/change/`);
    await expect(
      page.locator('div.readonly', { hasText: `Academy master of ${seed.good_tradition_name}` })
    ).toBeVisible();
    await page.locator('input[name="_continue"]').click();
    await expect(page.locator('.errornote')).toBeVisible();
    await expect(
      page.getByText(`${seed.good_tradition_name} does not teach Villainy.`)
    ).toBeVisible();
    await shot(testInfo, '05c-course-offer-refused.png', page, { fullPage: true });

    // Screen 5, third frame: a Villainy course on a role that names no Tradition.
    await page.goto(`/admin/arxii/skillcourseofferdetails/${seed.bare_course_id}/change/`);
    await expect(page.locator('div.readonly', { hasText: 'Academy master' }).first()).toBeVisible();
    await page.locator('input[name="_continue"]').click();
    await expect(page.locator('.errornote')).toBeVisible();
    await expect(
      page.getByText(
        'This role names no Tradition, so it cannot offer a course in Villainy. ' +
          'Set Teaches tradition on the role first.'
      )
    ).toBeVisible();
    await shot(testInfo, '05d-course-offer-refused-no-tradition.png', page, { fullPage: true });

    await page.context().close();
  });

  test('screen 6: character creation names what the Tradition teaches, and the training list follows', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(120_000);
    const page = await signedInPage(browser, ACCOUNT, PASSWORD);
    await page.goto('/characters/create');
    const steps = page.locator('ul[aria-label="Gift steps"]');
    await expect(steps).toBeVisible({ timeout: 30000 });

    // The Tradition step is done, so it is folded: open it. The chosen Tradition's own entry
    // is open, and its body carries the line.
    const stepNamed = (name: RegExp) =>
      steps.locator('> li').filter({
        has: page.locator('details.entry > summary .entry-name', { hasText: name }),
      });
    const tradition = stepNamed(/^Tradition$/);
    await openEntry(tradition);
    await expect(
      tradition.getByText('Teaches Reflection and Heroism', { exact: true })
    ).toBeVisible();
    await tradition.scrollIntoViewIfNeeded();
    await shot(testInfo, '06a-creation-tradition-teaches.png', tradition);

    // The training step: Reflection and Heroism are offered beside the ordinary Magic skill,
    // and Villainy is not.
    const training = stepNamed(/^What .* taught you$/);
    await openEntry(training);
    await expect(training).toContainText('Reflection');
    await expect(training).toContainText('Heroism');
    await expect(training).toContainText('Occult');
    await expect(training).not.toContainText('Villainy');
    await training.scrollIntoViewIfNeeded();
    await shot(testInfo, '06b-creation-training-list.png', training);

    await page.context().close();
  });

  test('screen 7, student: the card shows the waiting row, refuses no mentor and her own character, and asks a mentor', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, ACCOUNT, PASSWORD);
    await openGrowth(page, seed.entry_id);
    const card = page.getByTestId('training-card');
    await expect(card).toBeVisible({ timeout: 30000 });
    await expect(card.getByText('3 AP remaining this week')).toBeVisible();

    // Wren already asked Drusa Kell for Villainy: the row waits.
    const villainyRow = card.getByTestId('training-allocation-row').filter({ hasText: 'Villainy' });
    await expect(villainyRow.getByTestId('training-mentor-line')).toHaveText(
      `Mentor: ${seed.mentor_rated} · waiting for ${seed.mentor_rated} to agree`
    );
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07a-training-card-waiting-for-mentor.png', card);

    const skill = card.getByTestId('training-skill-select');
    await expect(skill.locator('option', { hasText: 'Villainy' })).toHaveCount(1);
    await expect(skill.locator('option', { hasText: 'Occult' })).toHaveCount(1);
    await skill.selectOption({ label: 'Villainy' });
    await card.locator('#training-add-ap').fill('3');
    const toasts = page.locator('[data-sonner-toast]');

    const attempt = async (mentor: string | null) => {
      if (mentor !== null) {
        await card.getByTestId('training-mentor-search').fill(mentor);
        await card.getByRole('button', { name: mentor, exact: true }).click();
      }
      await card.getByTestId('training-add-submit').click();
    };
    const settle = async (line: string, name: string) => {
      await toastShown(page, line);
      await card.scrollIntoViewIfNeeded();
      await shot(testInfo, name, page);
      await expect(toasts).toHaveCount(0, { timeout: 20000 });
    };

    // No mentor at all: refused, nothing saved.
    await attempt(null);
    await settle(
      'Villainy needs a teacher. Choose a mentor whose Tradition teaches it.',
      '07b-training-no-mentor.png'
    );

    // Another character her own player plays: refused, nothing saved.
    await attempt(seed.own_alt_name);
    await settle(
      'You cannot name another of your own characters as your mentor. ' +
        'Choose a mentor another player plays.',
      '07c-training-own-character.png'
    );

    // Occult with a mentor nobody plays: saved at once, and the mentor is asked. Nothing about
    // her is checked, so the card learns nothing about her.
    await skill.selectOption({ label: 'Occult' });
    await card.locator('#training-add-ap').fill('1');
    await attempt(seed.mentor_unrated);
    await toastShown(page, `Training allocated. ${seed.mentor_unrated} has been asked.`);
    const occultRow = card.getByTestId('training-allocation-row').filter({ hasText: 'Occult' });
    await expect(occultRow.getByTestId('training-mentor-line')).toHaveText(
      `Mentor: ${seed.mentor_unrated} · waiting for ${seed.mentor_unrated} to agree`
    );
    // The form is empty again: no skill, no typed mentor name, no result list left open.
    await expect(skill).toHaveValue('');
    await expect(card.getByTestId('training-mentor-search')).toHaveValue('');
    await expect(card.getByRole('button', { name: seed.mentor_unrated, exact: true })).toHaveCount(
      0
    );
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07d-training-asked-toast.png', page);

    // Leave the week as it was found: only the Villainy row, still waiting.
    await expect(toasts).toHaveCount(0, { timeout: 20000 });
    await occultRow.getByRole('button', { name: 'Remove' }).click();
    await expect(card.getByTestId('training-allocation-row')).toHaveCount(1);
    await expect(villainyRow).toBeVisible();

    await page.context().close();
  });

  test('screen 7, mentor: Drusa Kell and Aldric Voss are played by one account, which answers from its Mentoring card', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.mentor_username, seed.mentor_password);
    await openGrowth(page, seed.mentor_entry_id);
    const card = page.getByTestId('mentoring-card');
    await expect(card).toBeVisible({ timeout: 30000 });
    const toasts = page.locator('[data-sonner-toast]');

    const wrenRequest = card.getByTestId('mentoring-request-row').filter({
      hasText: `${seed.character_name} asks ${seed.mentor_rated} to teach her Villainy`,
    });
    const aldricRequest = card.getByTestId('mentoring-request-row').filter({
      hasText: `${seed.student_of_aldric} asks ${seed.mentor_good} to teach her Villainy`,
    });
    const taughtRow = card.getByTestId('mentoring-student-row').filter({
      hasText: `${seed.mentor_rated} teaches ${seed.student_taught} Villainy`,
    });
    await expect(wrenRequest).toBeVisible();
    await expect(wrenRequest.getByRole('button', { name: 'Accept' })).toBeVisible();
    await expect(wrenRequest.getByRole('button', { name: 'Decline' })).toBeVisible();
    await expect(aldricRequest).toBeVisible();
    await expect(taughtRow).toBeVisible();
    await expect(taughtRow.getByRole('button', { name: 'Stop' })).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07e-mentor-card-requests-and-teaching.png', card);

    // Aldric Voss's Tradition does not teach Villainy: Accept is refused to him, in his own
    // terms, and the request stays with Decline beside it.
    await aldricRequest.getByRole('button', { name: 'Accept' }).click();
    await toastShown(page, 'Your Tradition does not teach Villainy.');
    await expect(aldricRequest).toBeVisible();
    await expect(aldricRequest.getByRole('button', { name: 'Decline' })).toBeEnabled();
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07f-mentor-accept-refused.png', page);
    await expect(toasts).toHaveCount(0, { timeout: 20000 });

    // He declines instead: the request leaves his list, and Tamsin reads a line (07n).
    await aldricRequest.getByRole('button', { name: 'Decline' }).click();
    await toastShown(page, `You decline to teach ${seed.student_of_aldric} Villainy.`);
    await expect(aldricRequest).toHaveCount(0);
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07g-mentor-declined.png', page);
    await expect(toasts).toHaveCount(0, { timeout: 20000 });

    // Drusa Kell qualifies: the answer is the success sentence and the row moves to Teaching.
    await wrenRequest.getByRole('button', { name: 'Accept' }).click();
    await toastShown(page, `You agree to teach ${seed.character_name} Villainy.`);
    await expect(wrenRequest).toHaveCount(0);
    await expect(
      card.getByTestId('mentoring-student-row').filter({
        hasText: `${seed.mentor_rated} teaches ${seed.character_name} Villainy`,
      })
    ).toBeVisible();
    await expect(taughtRow).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07h-mentor-accepted.png', page);

    await page.context().close();
  });

  test('screen 7, game master: the card lists the requests to the NPCs she holds, refuses one by name and declines another', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.gm_username, seed.gm_password);
    await openGrowth(page, seed.gm_entry_id);
    const card = page.getByTestId('mentoring-card');
    await expect(card).toBeVisible({ timeout: 30000 });
    const toasts = page.locator('[data-sonner-toast]');

    const veyRequest = card.getByTestId('mentoring-request-row').filter({
      hasText: `${seed.student_of_vey} asks ${seed.npc_cannot_teach} to teach her Occult`,
    });
    const ilsaRequest = card.getByTestId('mentoring-request-row').filter({
      hasText: `${seed.student_of_ilsa} asks ${seed.npc_declined} to teach him Heroism`,
    });
    await expect(veyRequest).toBeVisible();
    await expect(ilsaRequest).toBeVisible();
    await expect(card.getByTestId('mentoring-request-row')).toHaveCount(2);
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07i-gm-card-two-npcs.png', card);

    // Magister Vey holds no Occult rating: refused by her name, the row stays.
    await veyRequest.getByRole('button', { name: 'Accept' }).click();
    await toastShown(page, `${seed.npc_cannot_teach} has no rating in Occult.`);
    await expect(veyRequest).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07j-gm-npc-accept-refused.png', page);
    await expect(toasts).toHaveCount(0, { timeout: 20000 });

    // Warden Ilsa Tarn's request is declined: the row is gone.
    await ilsaRequest.getByRole('button', { name: 'Decline' }).click();
    await toastShown(page, `You decline to teach ${seed.student_of_ilsa} Heroism.`);
    await expect(ilsaRequest).toHaveCount(0);
    await expect(veyRequest).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07k-gm-npc-declined.png', page);

    await page.context().close();
  });

  test('screen 7, student again: her row reads the mentor as agreed, and she is sent the two private lines', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(120_000);
    const seed = readSeed();
    const page = await signedInPage(browser, ACCOUNT, PASSWORD);
    await openGrowth(page, seed.entry_id);
    const card = page.getByTestId('training-card');
    await expect(card).toBeVisible({ timeout: 30000 });
    const villainyRow = card.getByTestId('training-allocation-row').filter({ hasText: 'Villainy' });
    await expect(villainyRow.getByTestId('training-mentor-line')).toHaveText(
      `Mentor: ${seed.mentor_rated}`
    );
    await expect(card.getByText('waiting for')).toHaveCount(0);
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07l-training-card-mentor-agreed.png', card);

    // The private lines the game sent her account: Wren's own, and Tamsin Reeve's, whom the
    // same account plays and whose request Aldric Voss declined.
    const agreed = page
      .locator('#messages div.rounded-md.p-3.transition-colors', {
        hasText: `${seed.mentor_rated} agreed to teach you Villainy.`,
      })
      .first();
    await expect(agreed).toBeVisible({ timeout: 30000 });
    await shot(testInfo, '07m-wren-private-line-agreed.png', agreed);
    const declined = page
      .locator('#messages div.rounded-md.p-3.transition-colors', {
        hasText: `${seed.mentor_good} declined to teach you Villainy.`,
      })
      .first();
    await expect(declined).toBeVisible();
    await shot(testInfo, '07n-private-line-declined.png', declined);

    await page.context().close();
  });

  test('screen 7, mentor stops: Drusa Kell presses Stop and Wren reads that she stopped', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(120_000);
    const seed = readSeed();
    const mentor = await signedInPage(browser, seed.mentor_username, seed.mentor_password);
    await openGrowth(mentor, seed.mentor_entry_id);
    const mentoring = mentor.getByTestId('mentoring-card');
    await expect(mentoring).toBeVisible({ timeout: 30000 });
    const wrenTeaching = mentoring.getByTestId('mentoring-student-row').filter({
      hasText: `${seed.mentor_rated} teaches ${seed.character_name} Villainy`,
    });
    await expect(wrenTeaching).toBeVisible();
    await wrenTeaching.getByRole('button', { name: 'Stop' }).click();
    await toastShown(mentor, `You stop teaching ${seed.character_name} Villainy.`);
    await expect(wrenTeaching).toHaveCount(0);
    await mentoring.scrollIntoViewIfNeeded();
    await shot(testInfo, '07o-mentor-stops-teaching.png', mentor);
    await mentor.context().close();

    const page = await signedInPage(browser, ACCOUNT, PASSWORD);
    await openGrowth(page, seed.entry_id);
    const card = page.getByTestId('training-card');
    await expect(card).toBeVisible({ timeout: 30000 });
    const villainyRow = card.getByTestId('training-allocation-row').filter({ hasText: 'Villainy' });
    await expect(villainyRow.getByText('Self-study')).toBeVisible();
    await expect(villainyRow.getByTestId('training-mentor-line')).toHaveCount(0);
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07p-training-card-after-stop.png', card);
    const stopped = page
      .locator('#messages div.rounded-md.p-3.transition-colors', {
        hasText: `${seed.mentor_rated} stopped teaching you Villainy.`,
      })
      .first();
    await expect(stopped).toBeVisible({ timeout: 30000 });
    await shot(testInfo, '07q-wren-private-line-stopped.png', stopped);

    await page.context().close();
  });

  test('screen 8: the trainer menu offers the Villainy course and cautions an outsider', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(120_000);
    const seed = readSeed();
    const page = await signedInPage(browser, ACCOUNT, PASSWORD);
    await page.goto('/game');
    await page
      .locator(
        `button[title="Connect as ${seed.character_name}"], ` +
          `button[title="Switch to ${seed.character_name}"], ` +
          `button[title="${seed.character_name}"]`
      )
      .first()
      .click();
    const people = page.getByTestId('npc-givers-block');
    await expect(people).toContainText(seed.trainer_name, { timeout: 45000 });
    await people.getByTestId(`talk-${seed.trainer_role_id}`).click();

    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: seed.trainer_name })).toBeVisible();
    await expect(dialog.getByRole('button', { name: /Villainy course/ })).toBeVisible();
    await expect(
      dialog.getByText(`Taught in the manner of ${seed.evil_tradition_name}`)
    ).toBeVisible();
    await expect(
      dialog.getByText('Your Tradition does not teach this. Sessions are harder for you.')
    ).toBeVisible();
    await shot(testInfo, '08a-trainer-menu-lantern-student.png', dialog);

    // Close without enrolling: the course is not taken.
    await page.keyboard.press('Escape');
    await page.context().close();
  });

  test('screen 8, Cinder Court student: the menu adds nothing, and the course is refused once the Tradition stops teaching Villainy', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(240_000);
    const seed = readSeed();
    const page = await signedInPage(browser, seed.cinder_username, seed.cinder_password);
    await page.goto('/game');
    await page
      .locator(
        `button[title="Connect as ${seed.cinder_character_name}"], ` +
          `button[title="Switch to ${seed.cinder_character_name}"], ` +
          `button[title="${seed.cinder_character_name}"]`
      )
      .first()
      .click();
    const people = page.getByTestId('npc-givers-block');
    await expect(people).toContainText(seed.trainer_name, { timeout: 45000 });
    await people.getByTestId(`talk-${seed.trainer_role_id}`).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: seed.trainer_name })).toBeVisible();
    const offer = dialog.getByRole('button', { name: /Villainy course/ });
    await expect(offer).toBeVisible();
    await expect(
      dialog.getByText(`Taught in the manner of ${seed.evil_tradition_name}`)
    ).toBeVisible();
    await expect(dialog.getByText('Your Tradition does not teach this.')).toHaveCount(0);
    await shot(testInfo, '08b-trainer-menu-cinder-student.png', dialog);

    // Staff take Villainy off the Cinder Court's list in the admin, as the demo's last frame
    // describes. The list is put back whatever happens next.
    const staff = await signedInPage(browser, seed.staff_username, seed.staff_password);
    const tradition = `/admin/arxii/tradition/${seed.evil_tradition_id}/change/`;
    try {
      await staff.goto(tradition);
      await staff.locator('#id_taught_skills_to').selectOption({ label: 'Villainy' });
      await staff.locator('#id_taught_skills_remove, #id_taught_skills_remove_link').click();
      await staff.locator('input[name="_continue"]').click();
      await expect(staff.locator('.messagelist .success')).toBeVisible();

      await offer.click();
      await expect(
        dialog.getByText(
          `${seed.trainer_name}'s Tradition no longer teaches Villainy, so this course is closed. ` +
            'Look for a trainer whose Tradition teaches it. Nothing was charged.'
        )
      ).toBeVisible();
      await shot(testInfo, '08c-trainer-menu-course-closed.png', dialog);
    } finally {
      await staff.goto(tradition);
      await staff.locator('#id_taught_skills_from').selectOption({ label: 'Villainy' });
      await staff.locator('#id_taught_skills_add, #id_taught_skills_add_link').click();
      await staff.locator('input[name="_continue"]').click();
      await expect(staff.locator('.messagelist .success')).toBeVisible();
      await staff.context().close();
    }

    await page.keyboard.press('Escape');
    await page.context().close();
  });
});
