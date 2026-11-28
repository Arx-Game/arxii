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
 * points) standing in the Cinder Hall with the Cinder Court master; three mentors; a creation
 * draft at the Gift stage with the Lantern Concord chosen; and a staff account for admin.
 *
 * One named PNG per screen of the approved demo (.demos/issue-5326-traditions-teach.html), each
 * written to the test's own output folder, which `just shot` lists when the run ends. The run
 * changes nothing a second run would trip over: the saved allocation is removed at the end, and
 * the Skill Course Offer Details page saved in screen 5 is saved with the values it already had.
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
  lantern_course_id: number;
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
    await shot(testInfo, '01-tradition-taught-skills.png', page);

    // Screen 2: the teaching settings page with the new number.
    await page.goto(`/admin/arxii/traditionteachingconfig/${seed.config_id}/change/`);
    await expect(page.locator('#id_other_tradition_course_difficulty')).toHaveValue('3');
    await shot(testInfo, '02-teaching-config-difficulty.png', page, { fullPage: true });

    // Screen 3: the modifier target, then the distinction's effect on it in the builder.
    await page.goto(`/admin/arxii/modifiertarget/${seed.modifier_target_id}/change/`);
    await expect(page.locator('#id_name')).toHaveValue('self_teaching');
    await shot(testInfo, '03a-modifier-target-self-teaching.png', page, { fullPage: true });
    await page.goto(`/admin/_distinction_builder/${seed.distinction_id}/`);
    await expect(page.getByRole('heading', { name: 'Distinction Builder' })).toBeVisible();
    await expect(page.locator('#effects-body')).toContainText(/self_teaching/);
    await page.locator('#effects-module').scrollIntoViewIfNeeded();
    await shot(testInfo, '03b-distinction-builder-effect.png', page, { fullPage: true });

    // Screen 4: the trainer role's page, naming the Tradition it teaches.
    await page.goto(`/admin/arxii/npcrole/${seed.evil_role_id}/change/`);
    await expect(page.locator('#id_teaches_tradition')).toHaveValue(String(seed.evil_tradition_id));
    await page.locator('.field-teaches_tradition').scrollIntoViewIfNeeded();
    await shot(testInfo, '04-npc-role-teaches-tradition.png', page, { fullPage: true });

    // Screen 5, first frame: the Cinder Court teaches Villainy, so the course saves. It is
    // saved with the values it already holds.
    await page.goto(`/admin/arxii/skillcourseofferdetails/${seed.evil_course_id}/change/`);
    await expect(page.getByText(`Academy master of ${seed.evil_tradition_name}`)).toBeVisible();
    await shot(testInfo, '05a-course-offer-before-save.png', page, { fullPage: true });
    await page.locator('input[name="_continue"]').click();
    await expect(page.locator('.messagelist .success')).toBeVisible();
    await shot(testInfo, '05b-course-offer-saved.png', page, { fullPage: true });

    // Screen 5, second frame: a Villainy course on a role of the Lantern Concord, which does
    // not teach Villainy. The save is refused and nothing changes.
    await page.goto(`/admin/arxii/skillcourseofferdetails/${seed.lantern_course_id}/change/`);
    await expect(page.getByText(`Academy master of ${seed.good_tradition_name}`)).toBeVisible();
    await page.locator('input[name="_continue"]').click();
    await expect(page.locator('.errornote')).toBeVisible();
    await expect(
      page.getByText(`${seed.good_tradition_name} does not teach Villainy.`)
    ).toBeVisible();
    await shot(testInfo, '05c-course-offer-refused.png', page, { fullPage: true });

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

  test('screen 7: the weekly training card refuses a Magic skill without a teacher and saves it with one', async ({
    browser,
  }, testInfo) => {
    test.setTimeout(180_000);
    const seed = readSeed();
    const page = await signedInPage(browser, ACCOUNT, PASSWORD);
    await page.goto(`/characters/${seed.entry_id}`);
    await page
      .getByRole('navigation', { name: 'Character sheet sections' })
      .getByRole('button', { name: 'Growth', exact: true })
      .click();
    const card = page.getByTestId('training-card');
    await expect(card).toBeVisible({ timeout: 30000 });
    await expect(card.getByText('6 AP remaining this week')).toBeVisible();
    const skill = card.getByTestId('training-skill-select');
    await expect(skill.locator('option', { hasText: 'Villainy' })).toHaveCount(1);
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
      await expect(page.getByText(line, { exact: true })).toBeVisible();
      await card.scrollIntoViewIfNeeded();
      await shot(testInfo, name, page);
      await expect(toasts).toHaveCount(0, { timeout: 20000 });
    };

    // No mentor at all.
    await attempt(null);
    await settle(
      'Villainy needs a teacher. Choose a mentor whose Tradition teaches it.',
      '07a-training-no-mentor.png'
    );

    // A mentor of her own Tradition, which does not teach Villainy.
    await attempt(seed.mentor_good);
    await settle(
      `${seed.mentor_good}'s Tradition does not teach Villainy. Choose a mentor whose Tradition does.`,
      '07b-training-mentor-wrong-tradition.png'
    );

    // A mentor of the Cinder Court who holds no Villainy rating.
    await attempt(seed.mentor_unrated);
    await settle(
      `${seed.mentor_unrated} has no rating in Villainy. Choose a mentor who has one.`,
      '07c-training-mentor-unrated.png'
    );

    // A mentor of the Cinder Court who holds a rating: saved.
    await attempt(seed.mentor_rated);
    await expect(page.getByText('Training allocated.', { exact: true })).toBeVisible();
    const row = card.getByTestId('training-allocation-row');
    await expect(row).toContainText('Villainy');
    await expect(row).toContainText(`Mentor: ${seed.mentor_rated}`);
    await card.scrollIntoViewIfNeeded();
    await shot(testInfo, '07d-training-mentor-teaches.png', page);

    // Leave the week as it was found, so a second run starts from the same place.
    await expect(toasts).toHaveCount(0, { timeout: 20000 });
    await card.getByRole('button', { name: 'Remove' }).click();
    await expect(card.getByTestId('training-empty')).toBeVisible();

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
    await people.getByTestId(`talk-${seed.evil_role_id}`).click();

    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: seed.trainer_name })).toBeVisible();
    await expect(dialog.getByRole('button', { name: /Villainy course/ })).toBeVisible();
    await expect(
      dialog.getByText(`Taught in the manner of ${seed.evil_tradition_name}`)
    ).toBeVisible();
    await expect(
      dialog.getByText('Your Tradition does not teach this. Sessions are harder for you.')
    ).toBeVisible();
    await shot(testInfo, '08-trainer-menu-caution.png', dialog);

    // Close without enrolling: the course is not taken.
    await page.keyboard.press('Escape');
    await page.context().close();
  });
});
