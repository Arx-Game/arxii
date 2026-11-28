import { readFileSync } from 'node:fs';

import { test, expect, type Locator, type Page, type TestInfo } from '@playwright/test';

/**
 * The Glimpse gives a card from each of four parts (#5292), against a live server (no
 * mocked /api/**). Runs with `--config e2e.backend.config.ts`.
 *
 * Needs the rows `integration_tests.live_seeds.seed_glimpse_spec` writes for its own
 * account, e2e_glimpse_account (the real-test workflow seeds it after the server starts
 * and writes the ids to the JSON file named by GLIMPSE_SEED): a creation draft at the
 * Gift stage with nothing of the Glimpse chosen; answers for Trigger, The Reflection, Tone
 * and Consequence that each give a card (Wonder gives Wonderstruck, "+Anima"; Defiance
 * gives Unbowed; Crisis gives Crisisborn; Radiant gives Glimmering) except Grief, which
 * gives none; two Witness & Secrecy answers, which give none; "Glimpse Mystery", the card
 * that marks a blackout and no memory; Maren Vosk, whose Glimpse was left for after
 * creation; Oriel Thane, who has no memory of theirs; and a staff account.
 *
 * What the page and the server have to agree on: the card is printed on the answer from
 * the catalogue, the save gives it, and the side panel reads the server's list of what
 * the Glimpse gave, so the panel is the proof that the card arrived without a reload.
 */

const ACCOUNT = 'e2e_glimpse_account';
const PASSWORD = 'TestPass123!';

interface Seed {
  draft_id: number;
  beginning_id: number;
  tone_tag_id: number;
  spare_card_id: number;
  witness_tag_id: number;
  choosing_tag_id: number;
  later_entry_id: number;
  later_sheet_id: number;
  amnesiac_entry_id: number;
  amnesiac_sheet_id: number;
  staff_username: string;
  staff_password: string;
}

interface DraftEntry {
  distinction_name: string;
  cost: number;
}

interface Draft {
  cg_points_remaining: number;
  draft_data: { distinctions?: DraftEntry[]; glimpse_tag_ids?: number[]; glimpse_memory?: string };
}

function readSeed(): Seed {
  return JSON.parse(
    readFileSync(process.env.GLIMPSE_SEED ?? '/tmp/glimpse-seed.json', 'utf8')
  ) as Seed;
}

async function logIn(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill(username);
  await page.getByPlaceholder('Password').fill(password);
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

async function csrfToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  return cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? '';
}

/** The draft as the server holds it now. */
async function savedDraft(page: Page, seed: Seed): Promise<Draft> {
  const res = await page.request.get(`/api/character-creation/drafts/${seed.draft_id}/`);
  expect(res.ok(), await res.text()).toBe(true);
  return (await res.json()) as Draft;
}

const held = (draft: Draft) =>
  Object.fromEntries(
    (draft.draft_data.distinctions ?? []).map((e) => [e.distinction_name, e.cost])
  );

/** A row of the side panel, by its label. */
const railRow = (page: Page, label: string): Locator =>
  page.locator('.record-rail .row').filter({ has: page.locator('dt', { hasText: label }) });

const answer = (page: Page, name: string): Locator =>
  page.locator('.part button.stance').filter({ has: page.locator('b', { hasText: name }) });

const way = (page: Page, name: string): Locator =>
  page.getByTestId('glimpse-ways').locator('button.stance').filter({ hasText: name });

async function shot(page: Page, info: TestInfo, name: string, target?: Locator) {
  const path = info.outputPath(name);
  if (target) {
    await target.screenshot({ path });
  } else {
    await page.screenshot({ path, fullPage: true });
  }
}

test.describe.configure({ mode: 'serial' });

test.describe('the Glimpse gives a card from each of four parts', () => {
  test('on the Gift stage an answer gives its card, free, with no reload', async ({
    page,
  }, info) => {
    const seed = readSeed();
    await page.setViewportSize({ width: 1440, height: 900 });
    await logIn(page, ACCOUNT, PASSWORD);
    await page.goto('/characters/create');
    await expect(page.locator('#glimpse-heading')).toBeVisible({ timeout: 20000 });
    const points = (await savedDraft(page, seed)).cg_points_remaining;
    const pointsText = await railRow(page, 'CG points').locator('dd').innerText();

    // The owner's paragraph, without the sentence that promised CG points, and three ways.
    const intro = page.locator('p.explain', {
      hasText: 'The Glimpse is the often traumatic event',
    });
    await expect(intro).toBeVisible();
    await expect(intro).not.toContainText('CG points');
    await expect(way(page, 'Create Glimpse in CG')).toHaveAttribute('aria-pressed', 'true');
    await expect(way(page, 'Amnesiac, No Memory of Glimpse')).toBeVisible();
    await expect(way(page, 'Create Glimpse Post-CG')).toBeVisible();
    await expect(page.getByText('Skip for now')).toHaveCount(0);

    // Every part's title is larger than an answer's name.
    const titleSize = await page
      .locator('#glimpse-axis-tone')
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    const nameSize = await answer(page, 'Wonder')
      .locator('b')
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(titleSize).toBeGreaterThan(nameSize * 1.4);

    // The rules are drawn, not only written: a line above each part and beside each
    // card. A declaration that reads a token nobody defines is dropped whole, and the
    // class still "has a rule" (both of these were missing until the demo review).
    const drawn = (el: Element, side: 'Top' | 'Left') => {
      const style = getComputedStyle(el);
      return {
        width: parseFloat(style[`border${side}Width`]),
        color: style[`border${side}Color`],
      };
    };
    const partRule = await page.locator('#glimpse-axis-tone').locator('..').evaluate(drawn, 'Top');
    expect(partRule.width).toBe(1);
    expect(partRule.color).not.toMatch(/rgba\(0, 0, 0, 0\)|transparent/);
    const cardRule = await answer(page, 'Wonder').locator('.bonus').evaluate(drawn, 'Left');
    expect(cardRule.width).toBe(2);
    expect(cardRule.color).not.toMatch(/rgba\(0, 0, 0, 0\)|transparent/);
    // The Glimpse's own title is drawn as its parts' are.
    const blockTitle = await page
      .locator('#glimpse-heading')
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(blockTitle).toBe(titleSize);
    // The blackout stands a part's distance below Trigger's answers.
    const gap = await page.evaluate(() => {
      const above = document.querySelector('#glimpse-axis-trigger')!.parentElement!;
      const blackout = document.querySelector('.blackout')!;
      return blackout.getBoundingClientRect().top - above.getBoundingClientRect().bottom;
    });
    expect(gap).toBeGreaterThanOrEqual(24);

    // The card is on the answer before it is picked; an answer with no card shows none.
    await expect(answer(page, 'Wonder').locator('.bonus')).toContainText('Wonderstruck');
    await expect(answer(page, 'Wonder').locator('.bonus')).toContainText('+Anima');
    await expect(answer(page, 'Grief').locator('.bonus')).toHaveCount(0);
    await expect(answer(page, 'Public').locator('.bonus')).toHaveCount(0);
    await shot(page, info, 'stage-before-any-answer-1440.png');

    // Picking the answer takes the card: the side panel names it, with no reload.
    await answer(page, 'Wonder').click();
    await expect(railRow(page, 'Tone').locator('dd')).toHaveText('Wonderstruck');
    await expect.poll(async () => held(await savedDraft(page, seed))).toEqual({ Wonderstruck: 0 });
    expect((await savedDraft(page, seed)).cg_points_remaining).toBe(points);
    await expect(railRow(page, 'CG points').locator('dd')).toHaveText(pointsText);
    await expect(page.locator('.part .price')).toHaveCount(0);

    // A second answer in the part replaces the first and swaps the card.
    await answer(page, 'Defiance').click();
    await expect(answer(page, 'Wonder')).toHaveAttribute('aria-pressed', 'false');
    await expect(railRow(page, 'Tone').locator('dd')).toHaveText('Unbowed');
    await expect.poll(async () => held(await savedDraft(page, seed))).toEqual({ Unbowed: 0 });

    // An answer with no card gives nothing, and nothing stands in for the card.
    await answer(page, 'Grief').click();
    await expect(railRow(page, 'Tone').locator('dd')).toHaveText('no card');
    await expect.poll(async () => held(await savedDraft(page, seed))).toEqual({});
    await shot(page, info, 'panel-answer-with-no-card.png', page.locator('.record-rail'));

    // The server refuses two answers in one part, in a part that gives a card and one
    // that gives none.
    const tags = (await (
      await page.request.get('/api/character-creation/glimpse-tags/')
    ).json()) as { id: number; axis: string }[];
    for (const [axis, label] of [
      ['REFLECTION', 'The Reflection'],
      ['WITNESS', 'Witness & Secrecy'],
    ]) {
      const two = tags.filter((tag) => tag.axis === axis).map((tag) => tag.id);
      expect(two.length).toBeGreaterThan(1);
      const refused = await page.request.patch(`/api/character-creation/drafts/${seed.draft_id}/`, {
        data: { draft_data: { glimpse_tag_ids: two.slice(0, 2) } },
        headers: { 'X-CSRFToken': await csrfToken(page) },
      });
      expect(refused.status()).toBe(400);
      expect(await refused.text()).toContain(`${label} takes one answer.`);
    }

    // Four parts answered: four cards, the CG points where they were.
    await answer(page, 'Wonder').click();
    await answer(page, 'Crisis').click();
    await answer(page, 'Radiant').click();
    await answer(page, 'Loss').click();
    await answer(page, 'Public').click();
    await expect(railRow(page, 'Consequence').locator('dd')).toHaveText('Bereft');
    await expect
      .poll(async () => held(await savedDraft(page, seed)))
      .toEqual({ Crisisborn: 0, Glimmering: 0, Wonderstruck: 0, Bereft: 0 });
    expect((await savedDraft(page, seed)).cg_points_remaining).toBe(points);
    await shot(page, info, 'stage-four-answers-1440.png');

    // A blackout takes The Reflection and Tone together and is marked by a card.
    await page.locator('.blackout button.stance').click();
    await expect(page.locator('#glimpse-axis-reflection')).toHaveCount(0);
    await expect(page.locator('#glimpse-axis-tone')).toHaveCount(0);
    await expect(page.locator('#glimpse-axis-trigger')).toBeVisible();
    await expect(page.locator('#glimpse-axis-witness')).toBeVisible();
    await expect(railRow(page, 'Tone').locator('dd')).toHaveText('not asked');
    await expect(railRow(page, 'Glimpse Mystery').locator('dd')).toHaveText('held');
    await expect
      .poll(async () => held(await savedDraft(page, seed)))
      .toEqual({ Crisisborn: 0, Bereft: 0, 'Glimpse Mystery': 0 });
    expect((await savedDraft(page, seed)).cg_points_remaining).toBe(points);
    await shot(page, info, 'stage-blackout-1440.png');

    // Unticking brings the earlier answers and their cards back.
    await page.locator('.blackout button.stance').click();
    await expect(answer(page, 'Wonder')).toHaveAttribute('aria-pressed', 'true');
    await expect
      .poll(async () => held(await savedDraft(page, seed)))
      .toEqual({ Crisisborn: 0, Glimmering: 0, Wonderstruck: 0, Bereft: 0 });

    // No memory: no part, the marking card alone. Post-CG: no part, no card.
    await way(page, 'Amnesiac, No Memory of Glimpse').click();
    await expect(page.locator('fieldset.part')).toHaveCount(0);
    await expect(railRow(page, 'Trigger').locator('dd')).toHaveText('not asked');
    await expect(railRow(page, 'Glimpse Mystery').locator('dd')).toHaveText('held');
    await expect
      .poll(async () => held(await savedDraft(page, seed)))
      .toEqual({ 'Glimpse Mystery': 0 });
    await shot(page, info, 'stage-no-memory-1440.png');
    await expect(page.locator('.glimpse-aside')).toContainText(
      'The character holds the Glimpse Mystery card'
    );
    await way(page, 'Create Glimpse Post-CG').click();
    await expect(page.locator('fieldset.part')).toHaveCount(0);
    await expect(page.locator('.glimpse-aside')).toHaveText(
      'The Glimpse is written from the character sheet after character creation, and each ' +
        'part gives its bonus then.'
    );
    // The line reads at the size of the paragraph above it.
    const sizes = await page.evaluate(() =>
      ['.glimpse-aside', 'p.explain'].map((selector) =>
        parseFloat(getComputedStyle(document.querySelector(selector)!).fontSize)
      )
    );
    expect(sizes[0]).toBe(sizes[1]);
    await expect(railRow(page, 'Trigger').locator('dd')).toHaveText('not asked');
    await expect(railRow(page, 'Glimpse Mystery')).toHaveCount(0);
    await expect.poll(async () => held(await savedDraft(page, seed))).toEqual({});
    expect((await savedDraft(page, seed)).cg_points_remaining).toBe(points);
    await shot(page, info, 'stage-later-1440.png');

    // Back to the first way: the answers were kept, and so the cards return.
    await way(page, 'Create Glimpse in CG').click();
    await expect(answer(page, 'Wonder')).toHaveAttribute('aria-pressed', 'true');
    await expect
      .poll(async () => held(await savedDraft(page, seed)))
      .toEqual({ Crisisborn: 0, Glimmering: 0, Wonderstruck: 0, Bereft: 0 });

    // A reload shows the same, and the page does not scroll sideways on a phone.
    await page.reload();
    await expect(railRow(page, 'Tone').locator('dd')).toHaveText('Wonderstruck');
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(answer(page, 'Wonder')).toBeVisible();
    const sideways = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(sideways).toBeLessThanOrEqual(0);
    await page.locator('#glimpse-heading').scrollIntoViewIfNeeded();
    await shot(page, info, 'stage-four-answers-390.png');
  });

  test('a part shows its explanation once staff write one, and a beginning can have no memory', async ({
    page,
    browser,
  }, info) => {
    const seed = readSeed();
    const staffContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const admin = await staffContext.newPage();
    await logIn(admin, seed.staff_username, seed.staff_password);

    // An explanation row for Tone, written in the admin.
    await admin.goto('/admin/arxii/cgexplanation/add/');
    await admin.locator('#id_key').fill('glimpse_axis_tone_explanation');
    await admin.locator('#id_text').fill('What the moment felt like from the inside.');
    await admin.locator('input[name="_save"]').click();
    await expect(admin.locator('.errornote')).toHaveCount(0);

    await page.setViewportSize({ width: 1440, height: 900 });
    await logIn(page, ACCOUNT, PASSWORD);
    await page.goto('/characters/create');
    const tone = page.locator('fieldset.part', { has: page.locator('#glimpse-axis-tone') });
    await expect(tone.locator('p.explain')).toHaveText(
      'What the moment felt like from the inside.',
      { timeout: 20000 }
    );
    await expect(tone.locator('.lead-in')).toHaveCount(0);
    // A part with no explanation keeps its lead-in.
    const trigger = page.locator('fieldset.part', { has: page.locator('#glimpse-axis-trigger') });
    await expect(trigger.locator('.lead-in')).toHaveText('The Circumstances Around Your Glimpse:');
    await shot(page, info, 'stage-explanation-under-tone.png', tone);

    // The Choosing has one answer, open to another path only: this draft is not asked it.
    await expect(page.locator('#glimpse-axis-choosing')).toHaveCount(0);
    // Staff open that answer to this draft's path, and the part appears after Trigger.
    // The admin's two-list widget keeps its own record of each list, so the move goes
    // through its own function, as the arrow between the lists does.
    const movePath = async (from: string, to: string) => {
      await admin.goto(`/admin/arxii/glimpsetag/${seed.choosing_tag_id}/change/`);
      await expect(admin.locator(`#${to}`)).toBeVisible();
      await admin.locator(`#${from}`).selectOption({ label: 'Strength Path (Prospect)' });
      await admin.evaluate(
        ([source, target]) => {
          const boxes = window as unknown as {
            SelectBox: { move: (source: string, target: string) => void };
          };
          boxes.SelectBox.move(source, target);
        },
        [from, to]
      );
      await admin.locator('input[name="_save"]').click();
      await expect(admin.locator('.errornote')).toHaveCount(0);
    };
    await movePath('id_paths_from', 'id_paths_to');
    await page.reload();
    await expect(page.locator('#glimpse-axis-choosing')).toBeVisible({ timeout: 20000 });
    const partOrder = await page
      .locator('fieldset.part > h3')
      .evaluateAll((titles) => titles.map((title) => title.id));
    expect(partOrder.slice(0, 3)).toEqual([
      'glimpse-axis-trigger',
      'glimpse-axis-choosing',
      'glimpse-axis-reflection',
    ]);
    const choosing = page.locator('fieldset.part', {
      has: page.locator('#glimpse-axis-choosing'),
    });
    await expect(choosing.locator('.bonus')).toHaveCount(0);
    await shot(page, info, 'stage-the-choosing-on-its-path.png', choosing);
    // Closed to this path again, the part is gone.
    await movePath('id_paths_to', 'id_paths_from');
    await page.reload();
    await expect(page.locator('#glimpse-axis-trigger')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('#glimpse-axis-choosing')).toHaveCount(0);

    // Staff tick the beginning as having no memory of the Glimpse.
    await admin.goto(`/admin/arxii/beginnings/${seed.beginning_id}/change/`);
    await admin.locator('#id_no_glimpse_memory').check();
    await admin.locator('input[name="_save"]').click();
    await expect(admin.locator('.errornote')).toHaveCount(0);

    await page.reload();
    await expect(page.locator('#glimpse-heading')).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId('glimpse-ways')).toHaveCount(0);
    await expect(page.locator('fieldset.part')).toHaveCount(0);
    await expect(page.getByText('Nothing of the Glimpse is asked.')).toBeVisible();
    // The draft's own choice is still "remembered" with four answers; the beginning wins.
    await expect(railRow(page, 'Glimpse Mystery').locator('dd')).toHaveText('held');
    const kick = await page.request.patch(`/api/character-creation/drafts/${seed.draft_id}/`, {
      data: { draft_data: { glimpse_memory: 'remembered' } },
      headers: { 'X-CSRFToken': await csrfToken(page) },
    });
    expect(kick.ok(), await kick.text()).toBe(true);
    expect(held((await kick.json()) as Draft)).toEqual({ 'Glimpse Mystery': 0 });
    await page.locator('#glimpse-heading').scrollIntoViewIfNeeded();
    await shot(page, info, 'stage-beginning-with-no-memory.png');

    // Put the beginning back for the next run.
    await admin.goto(`/admin/arxii/beginnings/${seed.beginning_id}/change/`);
    await admin.locator('#id_no_glimpse_memory').uncheck();
    await admin.locator('input[name="_save"]').click();
    await expect(admin.locator('.errornote')).toHaveCount(0);
    await staffContext.close();
  });

  test('on the sheet a Glimpse left for later gives its cards on one confirm, and is then final', async ({
    page,
    browser,
  }, info) => {
    const seed = readSeed();
    await page.setViewportSize({ width: 1440, height: 900 });
    await logIn(page, ACCOUNT, PASSWORD);
    const sheet = async () => {
      const res = await page.request.get(`/api/character-sheets/${seed.later_sheet_id}/`);
      expect(res.ok(), await res.text()).toBe(true);
      return (await res.json()) as {
        distinctions: { name: string; is_from_glimpse: boolean }[];
        magic: { aura: { glimpse_tags: { name: string }[]; can_finish_glimpse: boolean } };
      };
    };
    expect((await sheet()).distinctions).toEqual([]);

    await page.goto(`/characters/${seed.later_entry_id}`);
    await page.getByRole('button', { name: 'Magic', exact: true }).click();
    // A Glimpse left for later reads as unwritten, with no line about memory.
    await expect(page.getByText('You have not looked into your own aura yet.')).toBeVisible();
    await expect(page.getByText('No memory of the Glimpse.')).toHaveCount(0);
    await expect(page.getByText('Blacked out during the Glimpse.')).toHaveCount(0);
    await shot(page, info, 'sheet-later-unwritten.png');
    await page.getByTestId('finish-glimpse-button').click();
    const dialog = page.getByTestId('glimpse-editor-dialog');
    await expect(dialog).toBeVisible();

    // Picks are staged: nothing is saved by a click.
    await dialog.getByText('Crisis', { exact: true }).click();
    await dialog.getByText('Tone: how did it feel?').click();
    await expect(
      dialog.getByTestId('glimpse-card').filter({ hasText: 'Wonderstruck' })
    ).toBeVisible();
    await dialog.getByText('Wonder', { exact: true }).click();
    expect((await sheet()).magic.aura.glimpse_tags).toEqual([]);

    await dialog.getByTestId('glimpse-save-answers').click();
    const confirm = dialog.getByTestId('glimpse-confirm');
    await expect(confirm).toContainText('Trigger: Crisis');
    await expect(confirm).toContainText('Tone: Wonder');
    await expect(confirm).toContainText('These answers are final.');
    await shot(page, info, 'sheet-confirm-answers.png', dialog);
    await dialog.getByTestId('glimpse-confirm-save').click();
    await expect(confirm).toHaveCount(0);

    await expect
      .poll(async () => (await sheet()).distinctions.map((d) => d.name).sort())
      .toEqual(['Crisisborn', 'Wonderstruck']);
    expect((await sheet()).distinctions.every((d) => d.is_from_glimpse)).toBe(true);

    // An answered part is closed in the editor, and the server refuses a change.
    const closed = dialog
      .locator('[role="button"][aria-disabled="true"]')
      .filter({ hasText: 'Wonder' });
    await expect(closed).toHaveAttribute('aria-pressed', 'true');
    const auraId = (
      (await (await page.request.get(`/api/character-sheets/${seed.later_sheet_id}/`)).json()) as {
        magic: { aura: { id: number } };
      }
    ).magic.aura.id;
    const tags = (await (
      await page.request.get('/api/character-creation/glimpse-tags/')
    ).json()) as { id: number; axis: string; name: string }[];
    const defiance = tags.find((tag) => tag.name === 'Defiance')!;
    const change = await page.request.post(
      `/api/magic/character-auras/${auraId}/set-glimpse-tags/`,
      {
        data: { answers: [{ axis: 'TONE', tag_ids: [defiance.id] }] },
        headers: { 'X-CSRFToken': await csrfToken(page) },
      }
    );
    expect(change.status()).toBe(400);
    expect(await change.text()).toContain('Tone is already answered, and the answer is final.');
    expect((await sheet()).distinctions.map((d) => d.name).sort()).toEqual([
      'Crisisborn',
      'Wonderstruck',
    ]);

    // After the story is written, a part left unanswered is still open and gives its card.
    await dialog.getByLabel('Your Story').fill('It began with the bells.');
    await dialog.getByTestId('glimpse-save-story').click();
    await expect.poll(async () => (await sheet()).magic.aura.can_finish_glimpse).toBe(true);
    await dialog.getByText('Consequence: what did it leave behind?').click();
    await dialog.getByText('Loss', { exact: true }).click();
    await dialog.getByTestId('glimpse-save-answers').click();
    await dialog.getByTestId('glimpse-confirm-save').click();
    await expect
      .poll(async () => (await sheet()).distinctions.map((d) => d.name).sort())
      .toEqual(['Bereft', 'Crisisborn', 'Wonderstruck']);

    // Staff open the same editor on this character with every part open: the parts the
    // player can no longer change are not closed to them.
    const staffContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const staff = await staffContext.newPage();
    await logIn(staff, seed.staff_username, seed.staff_password);
    await staff.goto(`/characters/${seed.later_entry_id}`);
    await staff.getByRole('switch', { name: 'Edit' }).click();
    await staff.getByRole('button', { name: 'Magic', exact: true }).click();
    await staff.getByTestId('staff-glimpse-button').click();
    const staffDialog = staff.getByTestId('glimpse-editor-dialog');
    await expect(staffDialog).toBeVisible();
    await staffDialog.getByText('Tone: how did it feel?').click();
    const saved = staffDialog.locator('[role="button"][aria-pressed="true"]').filter({
      hasText: 'Wonder',
    });
    await expect(saved).toBeVisible();
    await expect(staffDialog.locator('[aria-disabled="true"]')).toHaveCount(0);
    await shot(staff, info, 'sheet-staff-editor-every-part-open.png', staffDialog);
    await staffContext.close();
  });

  test('with no memory the player is refused until staff set the memory to remembered', async ({
    page,
    browser,
  }, info) => {
    const seed = readSeed();
    await page.setViewportSize({ width: 1440, height: 900 });
    await logIn(page, ACCOUNT, PASSWORD);
    const sheet = async () =>
      (await (
        await page.request.get(`/api/character-sheets/${seed.amnesiac_sheet_id}/`)
      ).json()) as {
        distinctions: { name: string }[];
        magic: { aura: { id: number; glimpse_memory: string; can_finish_glimpse: boolean } };
      };
    const before = await sheet();
    expect(before.magic.aura.glimpse_memory).toBe('no_memory');
    expect(before.magic.aura.can_finish_glimpse).toBe(false);
    expect(before.distinctions.map((d) => d.name)).toEqual(['Glimpse Mystery']);

    await page.goto(`/characters/${seed.amnesiac_entry_id}`);
    await page.getByRole('button', { name: 'Magic', exact: true }).click();
    await expect(page.getByText('No memory of the Glimpse.')).toBeVisible();
    await expect(page.getByTestId('finish-glimpse-button')).toHaveCount(0);
    await shot(page, info, 'sheet-no-memory.png');

    const tags = (await (
      await page.request.get('/api/character-creation/glimpse-tags/')
    ).json()) as { id: number; name: string }[];
    const wonder = tags.find((tag) => tag.name === 'Wonder')!;
    const write = async () =>
      page.request.post(`/api/magic/character-auras/${before.magic.aura.id}/set-glimpse-tags/`, {
        data: { answers: [{ axis: 'TONE', tag_ids: [wonder.id] }] },
        headers: { 'X-CSRFToken': await csrfToken(page) },
      });
    const refused = await write();
    expect(refused.status()).toBe(400);
    expect(await refused.text()).toContain('This character has no memory of their Glimpse.');
    const story = await page.request.post(
      `/api/magic/character-auras/${before.magic.aura.id}/set-glimpse-prose/`,
      { data: { text: 'I remember.' }, headers: { 'X-CSRFToken': await csrfToken(page) } }
    );
    expect(story.status()).toBe(400);

    // Staff flip the switch in the staff sheet editor.
    const staffContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const staff = await staffContext.newPage();
    await logIn(staff, seed.staff_username, seed.staff_password);
    await staff.goto(`/characters/${seed.amnesiac_entry_id}`);
    await staff.getByRole('switch', { name: 'Edit' }).click();
    await staff.getByRole('button', { name: 'Magic', exact: true }).click();
    const memory = staff.getByLabel('Memory of the Glimpse');
    await expect(memory).toHaveValue('no_memory');
    await shot(staff, info, 'sheet-staff-memory.png', staff.getByTestId('staff-glimpse'));

    // Blacked out: one line says so, and the player's editor offers neither The
    // Reflection nor Tone.
    await memory.selectOption('blacked_out');
    await expect.poll(async () => (await sheet()).magic.aura.glimpse_memory).toBe('blacked_out');
    await page.reload();
    await page.getByRole('button', { name: 'Magic', exact: true }).click();
    await expect(page.getByText('Blacked out during the Glimpse.')).toBeVisible();
    await page.getByTestId('finish-glimpse-button').click();
    const editor = page.getByTestId('glimpse-editor-dialog');
    await expect(editor.getByText('Trigger: what was happening?')).toBeVisible();
    await expect(editor.getByText('Consequence: what did it leave behind?')).toBeVisible();
    await expect(editor.getByText('The Reflection: what did you see in yourself?')).toHaveCount(0);
    await expect(editor.getByText('Tone: how did it feel?')).toHaveCount(0);
    // The Choosing's one answer is another path's, so this character is not asked it.
    await expect(editor.getByText('The Choosing: how did it claim you?')).toHaveCount(0);
    await shot(page, info, 'sheet-blacked-out-editor.png');
    const blackedOut = await write();
    expect(blackedOut.status()).toBe(400);

    await memory.selectOption('remembered');
    await expect.poll(async () => (await sheet()).magic.aura.glimpse_memory).toBe('remembered');
    await staffContext.close();

    // The same request is now accepted and gives the card; the marking card stays.
    const accepted = await write();
    expect(accepted.status(), await accepted.text()).toBe(200);
    expect((await sheet()).distinctions.map((d) => d.name).sort()).toEqual([
      'Glimpse Mystery',
      'Wonderstruck',
    ]);
  });

  test('the admin refuses a card under a Witness answer and saves one under a Tone answer', async ({
    browser,
  }, info) => {
    const seed = readSeed();
    const staffContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const admin = await staffContext.newPage();
    await logIn(admin, seed.staff_username, seed.staff_password);

    // A Witness & Secrecy answer gives no card.
    await admin.goto(`/admin/arxii/glimpsetag/${seed.witness_tag_id}/change/`);
    await expect(admin.getByRole('heading', { name: /the card it gives/i }).first()).toBeVisible();
    await expect(admin.locator('[name="distinction_offers-0-arrives_as"]')).toHaveCount(0);
    await admin.locator('#id_distinction_offers-0-distinction').evaluate((el, id) => {
      const select = el as HTMLSelectElement;
      select.add(new Option('Spare Card', String(id), true, true));
    }, seed.spare_card_id);
    await admin.locator('input[name="_save"]').click();
    await expect(admin.locator('.errornote')).toBeVisible();
    await expect(admin.getByText('An answer to Witness & Secrecy gives no card.')).toBeVisible();
    await shot(admin, info, 'admin-witness-answer-refused.png');

    // A card an answer of another part gives (Crisisborn, Trigger's) cannot go under a
    // Tone answer.
    const catalogue = (await (
      await admin.request.get('/api/character-creation/glimpse-tags/')
    ).json()) as { name: string; offers: { distinction_id: number }[] }[];
    const crisisborn = catalogue.find((tag) => tag.name === 'Crisis')!.offers[0].distinction_id;
    await admin.goto(`/admin/arxii/glimpsetag/${seed.tone_tag_id}/change/`);
    await admin.locator('#id_distinction_offers-0-distinction').evaluate((el, id) => {
      const select = el as HTMLSelectElement;
      select.add(new Option('Crisisborn', String(id), true, true));
    }, crisisborn);
    await admin.locator('input[name="_save"]').click();
    await expect(admin.locator('.errornote')).toBeVisible();
    await expect(
      admin.getByText('An answer to another part of the Glimpse already gives this card.')
    ).toBeVisible();
    await shot(admin, info, 'admin-card-of-another-part-refused.png');

    // Grief (Tone) has no card: staff give it one, and it arrives bundled.
    await admin.goto(`/admin/arxii/glimpsetag/${seed.tone_tag_id}/change/`);
    await admin.locator('#id_distinction_offers-0-distinction').evaluate((el, id) => {
      const select = el as HTMLSelectElement;
      select.add(new Option('Spare Card', String(id), true, true));
    }, seed.spare_card_id);
    await admin.locator('input[name="_continue"]').click();
    await expect(admin.locator('.errornote')).toHaveCount(0);
    await expect(admin.getByText('Bundled free with its opener').first()).toBeVisible();
    await shot(admin, info, 'admin-answer-gives-one-card.png');

    // The card is now the Glimpse's: the Identity stage cannot offer it.
    const lines = (await (
      await admin.request.get('/api/character-creation/glimpse-tags/')
    ).json()) as { id: number; offers: { name: string }[] }[];
    expect(lines.find((tag) => tag.id === seed.tone_tag_id)!.offers.map((o) => o.name)).toEqual([
      'Spare Card',
    ]);

    // Take the line off again, so a second run starts from the same place.
    await admin.locator('#id_distinction_offers-0-DELETE').check();
    await admin.locator('input[name="_save"]').click();
    await expect(admin.locator('.errornote')).toHaveCount(0);
    await staffContext.close();
  });
});
