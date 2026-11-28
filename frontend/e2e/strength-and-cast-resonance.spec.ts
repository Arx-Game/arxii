import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { test, expect, type Locator, type Page } from '@playwright/test';

/**
 * Choosing what gives a character strength in creation, and the resonance a cast is worked
 * in (#5231), against a live server (no mocked /api/**). Runs with
 * `--config e2e.backend.config.ts`.
 *
 * Needs the rows `integration_tests.live_seeds.seed_strength_spec` writes for its own account,
 * e2e_strength_account (the real-test workflow seeds it after the server starts and writes the
 * ids to the JSON file named by STRENGTH_SEED): a creation draft at the Gift stage with its
 * tradition, gift and techniques chosen and no resonance picked; the 24 resonances of the
 * approved demo (Fera has no colour of its own yet); a caster, Ysmay Vale, played by the same
 * account, in a scene that is running, whose Gift thread holds Sereni (Primal, her usual) and
 * Praedari (Abyssal, kindled); and a staff account for the admin half.
 *
 * The expectations were written from the approved demo and spec before anything ran:
 *
 * Creation: a fresh step shows the eight Primal feelings, the question about other people with
 * three answers and a disabled slider on a grey aura, and not the second pick's question; one
 * feeling is pressed at a time; "hurting" shows the eight Abyssal resonances; the slider
 * divides ten points; an even split reads Primal; "neither" gives all ten points to the
 * feeling; a colour set on a resonance in admin is the colour drawn after a reload; the
 * saved draft holds exactly the two weights and a reload shows the same picks; a draft with
 * no feeling is refused with "Pick the feeling that gives you strength."
 *
 * Casting: the picker lists both resonances, Sereni as the usual one and Praedari marked
 * stronger; a cast worked in Sereni lists no kindled line and leaves corruption alone; the
 * same cast worked in Praedari lists a kindled line of 9 and raises her Praedari corruption
 * by 2. The 9 is the strength row's cast power 6 at Abyssal's boost of 150 percent, 6 * 150
 * // 100. The 2 is the technique's intensity 20 times Abyssal's coefficient and tier 1's
 * (each 10 tenths, so 1.0) = 20, of which the caster, 20 percent Abyssal and under the
 * full-from share of 50, takes the light 10 percent: 20 * 10 / 100 = 2.
 *
 * Also expected, from the fixes made after the first live run: the resonance step stays open
 * once the player has picked in it (a draft that arrives already complete shows it folded, as
 * any finished step is); "hurting" presses no card, saves nothing and leaves the slider off
 * until the player picks; the aura caption and its sentence read at 4.5 to 1 or better on the
 * plate; a draft with nothing picked says "Pick the feeling that gives you strength."; the
 * result of a cast worked in a kindled resonance says "Your kindled Praedari strengthened the
 * cast." above the power ledger, and the result of one worked in the usual resonance says no
 * such thing; the "You earned N Praedari." line reaches her in the Messages section of her
 * character sheet.
 *
 * Run it once per freshly seeded database, never twice on one. The first test changes Fera's
 * colour and the draft's picks, and each cast worked in Praedari earns her 15 more Praedari, so
 * after the fourth her Abyssal share reaches 50 percent and she takes the full corruption (20)
 * instead of the light part (2); the "+ 2" holds only on a fresh seed. The workflow seeds a
 * fresh database for every run.
 *
 * Screenshots go to docs/reviews/5231/ under the repo root only with EVIDENCE_SHOTS=1.
 */

const ACCOUNT = 'e2e_strength_account';
const FIGHT_ACCOUNT = 'e2e_strength_fight_account';
const PASSWORD = 'TestPass123!';
/** A vivid colour set through admin; the plate must draw it and not the default grey. */
const ADMIN_COLOUR = '#D4421E';

interface Seed {
  draft_id: number;
  feeling_name: string;
  second_feeling_name: string;
  outward_name: string;
  second_outward_name: string;
  admin_feeling_id: number;
  admin_feeling_name: string;
  caster_id: number;
  scene_id: number;
  scene_name: string;
  technique_name: string;
  usual_name: string;
  kindled_name: string;
  usual_row_id: number;
  kindled_row_id: number;
  abyssal_affinity_id: number;
  kindling_config_id: number;
  corruption_config_id: number;
  drift_config_id: number;
  staff_username: string;
  staff_password: string;
}

/** What `seed_strength_fight_spec` wrote for the fight test. */
interface FightSeed {
  character_id: number;
  character_name: string;
  encounter_id: number;
  participant_id: number;
  opponent_name: string;
  technique_name: string;
  usual_name: string;
  kindled_name: string;
  staff_username: string;
  staff_password: string;
}

interface Draft {
  draft_data: { gift_resonance_weights?: { resonance_id: number; weight: number }[] };
  stage_errors: Record<string, string[]>;
}

const PRIMAL_EIGHT = ['Arderi', 'Sereni', 'Audax', 'Medita', 'Fera', 'Civitas', 'Firma', 'Vola'];
const CELESTIAL_EIGHT = [
  'Bene',
  'Liberare',
  'Fidelis',
  'Misera',
  'Fortis',
  'Honoris',
  'Verax',
  'Copperi',
];
const ABYSSAL_EIGHT = [
  'Praedari',
  'Dominari',
  'Perfidus',
  'Maligna',
  'Tremora',
  'Saevus',
  'Insidia',
  'Despari',
];

/** Gift is stage 6 (`Stage.GIFT`). */
const GIFT_STAGE = '6';
const FEELING_QUESTION = 'Which feeling gives you strength';
const OUTWARD_QUESTION = 'Which of these gives you strength';
const STRENGTH_CASTER = 'Ysmay Vale';
const NO_FEELING = 'Pick the feeling that gives you strength.';

function readSeed(): Seed {
  return JSON.parse(
    readFileSync(process.env.STRENGTH_SEED ?? '/tmp/strength-seed.json', 'utf8')
  ) as Seed;
}

function readFightSeed(): FightSeed {
  return JSON.parse(
    readFileSync(process.env.STRENGTH_FIGHT_SEED ?? '/tmp/strength-fight-seed.json', 'utf8')
  ) as FightSeed;
}

const SHOT_DIR = join(process.cwd(), '..', 'docs', 'reviews', '5231');

/** A screenshot of `target`, kept only when EVIDENCE_SHOTS is set (CI writes none). */
async function shot(target: Locator, name: string) {
  if (!process.env.EVIDENCE_SHOTS) return;
  mkdirSync(SHOT_DIR, { recursive: true });
  await target.screenshot({ path: join(SHOT_DIR, name) });
}

/** A screenshot of the visible part of `page`, kept only when EVIDENCE_SHOTS is set. */
async function shotPage(page: Page, name: string) {
  if (!process.env.EVIDENCE_SHOTS) return;
  mkdirSync(SHOT_DIR, { recursive: true });
  await page.screenshot({ path: join(SHOT_DIR, name) });
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

function draftSaved(page: Page) {
  return page.waitForResponse(
    (r) => r.url().includes('/api/character-creation/drafts/') && r.request().method() === 'PATCH'
  );
}

/** The aura plate's mean colour and how much of it is dark, read from the drawn canvas. */
async function plate(page: Page) {
  return page.locator('.strength-aura canvas').evaluate((canvas: HTMLCanvasElement) => {
    const context = canvas.getContext('2d');
    if (!context) throw new Error('no 2d context');
    const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
    let n = 0;
    let dark = 0;
    const sum = [0, 0, 0];
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] < 128) continue;
      n += 1;
      sum[0] += data[i];
      sum[1] += data[i + 1];
      sum[2] += data[i + 2];
      if (0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2] < 60) dark += 1;
    }
    const mean = sum.map((v) => (n ? v / n : 0));
    return {
      n,
      r: mean[0],
      g: mean[1],
      b: mean[2],
      darkShare: n ? dark / n : 0,
      spread: Math.max(...mean) - Math.min(...mean),
    };
  });
}

function feelings(page: Page) {
  return page.getByRole('group', { name: FEELING_QUESTION, exact: true });
}
function outwards(page: Page) {
  return page.getByRole('group', { name: OUTWARD_QUESTION, exact: true });
}
function card(group: Locator, name: string) {
  return group.getByRole('button', { name: new RegExp(`^${name}\\b`) });
}

/** The resonance step's own fold in the Gift funnel. */
function stepEntry(page: Page) {
  return page
    .locator('details.entry')
    .filter({ has: page.locator('.entry-name', { hasText: 'Your Resonance' }) });
}

/**
 * A draft that arrives with the step already complete shows it folded, with its summary line,
 * as any finished step is. The player opens it by clicking its heading.
 */
async function openFinishedStep(page: Page, summary: string) {
  const entry = stepEntry(page);
  await expect(entry).toBeVisible({ timeout: 20000 });
  await expect(entry.locator('.entry-gloss')).toHaveText(summary, { timeout: 20000 });
  await expect(page.locator('.strength-step')).toBeHidden({ timeout: 10000 });
  await entry.locator('summary').click();
  await expect(page.locator('.strength-step')).toBeVisible();
}

/** The colour `css` names as [r, g, b], read through a canvas so any computed format works. */
async function rgbOf(locator: Locator, property: 'color' | 'backgroundColor') {
  return locator.evaluate((element, prop) => {
    const canvas = document.createElement('canvas');
    canvas.width = 1;
    canvas.height = 1;
    const context = canvas.getContext('2d') as CanvasRenderingContext2D;
    context.fillStyle = getComputedStyle(element)[prop as 'color'];
    context.fillRect(0, 0, 1, 1);
    const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
    return [r, g, b];
  }, property);
}

/** WCAG contrast ratio between two [r, g, b] colours. */
function contrastRatio(a: number[], b: number[]): number {
  const luminance = ([r, g, bl]: number[]) => {
    const [lr, lg, lb] = [r, g, bl].map((channel) => {
      const c = channel / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
  };
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

test.describe.configure({ mode: 'serial' });

test.describe('what gives a character strength', () => {
  test.use({ viewport: { width: 1280, height: 900 } });
  // Two logins, an admin context, two casts and a six-second wait between them.
  test.setTimeout(90_000);

  test('creation: a feeling, a side and a balance, with the aura following', async ({
    page,
    browser,
  }) => {
    const seed = readSeed();
    await logIn(page, ACCOUNT, PASSWORD);
    await page.goto('/characters/create');
    const step = page.locator('.strength-step');
    await expect(step).toBeVisible({ timeout: 20000 });

    // A1: a fresh step.
    for (const name of PRIMAL_EIGHT) {
      await expect(card(feelings(page), name), `${name} is offered`).toBeVisible();
    }
    test.info().annotations.push({
      type: 'primal cards shown',
      description: String(await feelings(page).getByRole('button').count()),
    });
    for (const answer of ['Helping them', 'Hurting them', 'Neither']) {
      await expect(step.getByRole('button', { name: answer, exact: true })).toBeVisible();
    }
    await expect(step.getByText(OUTWARD_QUESTION, { exact: true })).toHaveCount(0);
    await expect(step.locator('input[type="range"]')).toBeDisabled();
    await expect(feelings(page).locator('[aria-pressed="true"]')).toHaveCount(0);
    const grey = await plate(page);
    expect(grey.n).toBeGreaterThan(1000);
    expect(grey.spread, `a grey plate, saw ${JSON.stringify(grey)}`).toBeLessThan(25);
    // The step's own paragraph rules reach the page, past `.entry-prose p`: a question has
    // 1.5rem above it and 0.2rem below, the intro 0.6rem below, at the page's root font size.
    const rootPx = await page.evaluate(() =>
      parseFloat(getComputedStyle(document.documentElement).fontSize)
    );
    const margins = await step
      .locator('.strength-ask')
      .first()
      .evaluate((element) => ({
        top: parseFloat(getComputedStyle(element).marginTop),
        bottom: parseFloat(getComputedStyle(element).marginBottom),
      }));
    expect(margins.top).toBeCloseTo(1.5 * rootPx, 1);
    expect(margins.bottom).toBeCloseTo(0.2 * rootPx, 1);
    const introBottom = await step
      .locator('.strength-intro')
      .evaluate((element) => parseFloat(getComputedStyle(element).marginBottom));
    expect(introBottom).toBeCloseTo(0.6 * rootPx, 1);
    await shot(step, 'built-screen1-empty.png');

    // A8, first form: nothing picked at all is refused in the player's words, in the API and
    // in the contents rail beside the Gift stage.
    const fresh = await savedDraft(page, seed);
    expect(fresh.draft_data.gift_resonance_weights ?? []).toEqual([]);
    expect(fresh.stage_errors[GIFT_STAGE]).toEqual([NO_FEELING]);
    await expect(page.locator('.toc-note').first()).toContainText(NO_FEELING);

    // A2: exactly one feeling at a time.
    const arderi = card(feelings(page), seed.feeling_name);
    const audax = card(feelings(page), seed.second_feeling_name);
    let saved = draftSaved(page);
    await arderi.click();
    expect((await saved).status()).toBe(200);
    // The step stays open after the first pick, with no click on its heading: the second
    // question, the slider and the plate are still in view.
    await expect(step).toBeVisible();
    await expect(
      step.getByText('Does what you do to other people give you strength')
    ).toBeVisible();
    await expect(step.locator('input[type="range"]')).toBeVisible();
    await expect(page.locator('.strength-aura canvas')).toBeVisible();
    await expect(arderi).toHaveAttribute('aria-pressed', 'true');
    // Picking a feeling answers nothing about other people: none of the three answers is
    // pressed for her, and nothing says her points all go to the feeling yet.
    for (const answer of ['Helping them', 'Hurting them', 'Neither']) {
      await expect(step.getByRole('button', { name: answer, exact: true })).toHaveAttribute(
        'aria-pressed',
        'false'
      );
    }
    await expect(step.locator('.strength-skipped')).toHaveCount(0);
    await shot(step, 'built-screen1-first-pick-step-open.png');
    // The frame around the step: the funnel entry "Your Resonance", open, with its heading and
    // its place in the funnel, and the step inside it.
    const frame = page
      .locator('ul[aria-label="Gift steps"] > li')
      .filter({ has: page.locator('.entry-name', { hasText: 'Your Resonance' }) });
    await expect(frame.locator('details.entry')).toHaveAttribute('open', '');
    await expect(frame.locator('.entry-name')).toHaveText('Your Resonance');
    await expect(frame.locator('.entry-tag')).toContainText('Step 4 of 5');
    await expect(frame.locator('.strength-step')).toBeVisible();
    await shot(frame, 'built-stage-frame.png');
    await frame.scrollIntoViewIfNeeded();
    await shotPage(page, 'built-stage-leaf.png');
    await expect(feelings(page).locator('[aria-pressed="true"]')).toHaveCount(1);
    saved = draftSaved(page);
    await audax.click();
    expect((await saved).status()).toBe(200);
    await expect(audax).toHaveAttribute('aria-pressed', 'true');
    await expect(arderi).toHaveAttribute('aria-pressed', 'false');
    await expect(feelings(page).locator('[aria-pressed="true"]')).toHaveCount(1);
    saved = draftSaved(page);
    await arderi.click();
    expect((await saved).status()).toBe(200);
    await expect(feelings(page).locator('[aria-pressed="true"]')).toHaveCount(1);
    await expect(arderi).toHaveAttribute('aria-pressed', 'true');
    const orange = await plate(page);
    expect(orange.r, `an orange plate, saw ${JSON.stringify(orange)}`).toBeGreaterThan(
      orange.b + 40
    );

    // A3: "hurting" shows the eight Abyssal resonances and presses none of them: nothing is
    // saved and the slider stays off until the player picks one herself.
    const hurting = step.getByRole('button', { name: 'Hurting them', exact: true });
    await hurting.click();
    await expect(hurting).toHaveAttribute('aria-pressed', 'true');
    await expect(step.getByText(OUTWARD_QUESTION, { exact: true })).toBeVisible();
    for (const name of ABYSSAL_EIGHT) {
      await expect(card(outwards(page), name), `${name} is offered`).toBeVisible();
    }
    const slider = step.locator('input[type="range"]');
    // No count of the cards: the database is shared with the other specs' seeds, which may add
    // resonances of their own. Each named one is offered above.
    await expect(outwards(page).locator('[aria-pressed="true"]')).toHaveCount(0);
    await expect(slider).toBeDisabled();
    // She chose a side and has not picked from it yet: the step does not tell her there is
    // no second pick.
    await expect(step.locator('.strength-skipped')).toHaveCount(0);
    await page.waitForTimeout(1000); // time for a save, were one going to be sent
    const afterSide = (await savedDraft(page, seed)).draft_data.gift_resonance_weights ?? [];
    expect(afterSide, 'only the feeling is saved').toHaveLength(1);
    await shot(step, 'built-screen1-hurting-chosen.png');
    const praedari = card(outwards(page), seed.outward_name);
    saved = draftSaved(page);
    await praedari.click();
    expect((await saved).status()).toBe(200);
    await expect(praedari).toHaveAttribute('aria-pressed', 'true');
    await expect(outwards(page).locator('[aria-pressed="true"]')).toHaveCount(1);
    await expect(slider).toBeEnabled();
    await shot(step, 'built-screen1-picks.png');

    // The slider divides ten points: 8 for the feeling and 2 for the second pick.
    saved = draftSaved(page);
    await slider.fill('2');
    expect((await saved).status()).toBe(200);
    await expect(step.locator('.strength-pts')).toHaveText(
      `${seed.feeling_name} 8 · ${seed.outward_name} 2`
    );
    const mostlyOrange = await plate(page);
    // Mostly the feeling's colour, with streaks of the second (dark) one.
    expect(mostlyOrange.r, `orange leads, saw ${JSON.stringify(mostlyOrange)}`).toBeGreaterThan(
      mostlyOrange.b + 40
    );
    expect(mostlyOrange.darkShare).toBeGreaterThan(0.02);
    expect(mostlyOrange.darkShare).toBeLessThan(0.5);
    test.info().annotations.push({
      type: 'plate at 8 and 2',
      description: JSON.stringify(mostlyOrange),
    });
    // The caption and its sentence read on the night plate at 4.5 to 1 or better.
    const plateColour = await rgbOf(step.locator('.strength-plate'), 'backgroundColor');
    for (const selector of ['.strength-named', '.strength-said']) {
      const text = await rgbOf(step.locator(selector), 'color');
      const ratio = contrastRatio(text, plateColour);
      test.info().annotations.push({
        type: `contrast of ${selector}`,
        description: `${ratio.toFixed(1)} to 1 (${text} on ${plateColour})`,
      });
      expect(ratio, `${selector} on the plate`).toBeGreaterThanOrEqual(4.5);
    }
    await shot(step, 'built-screen2-balance-8-2.png');

    // A7: the server holds exactly the two weights, and a reload shows the same picks.
    const kept = (await savedDraft(page, seed)).draft_data.gift_resonance_weights ?? [];
    expect(kept).toHaveLength(2);
    expect(kept.map((pick) => pick.weight).sort((a, b) => b - a)).toEqual([8, 2]);
    await page.reload();
    // The draft arrives complete, so the step is folded with its summary line.
    await openFinishedStep(page, `${seed.feeling_name}, ${seed.outward_name}`);
    await expect(card(feelings(page), seed.feeling_name)).toHaveAttribute('aria-pressed', 'true');
    await expect(card(outwards(page), seed.outward_name)).toHaveAttribute('aria-pressed', 'true');
    await expect(step.locator('input[type="range"]')).toHaveValue('2');
    await expect(step.locator('.strength-pts')).toHaveText(
      `${seed.feeling_name} 8 · ${seed.outward_name} 2`
    );

    // A4: an even split reads Primal.
    saved = draftSaved(page);
    await step.locator('input[type="range"]').fill('5');
    expect((await saved).status()).toBe(200);
    await expect(step.locator('.strength-pts')).toHaveText(
      `${seed.feeling_name} 5 · ${seed.outward_name} 5`
    );
    await expect(step.locator('.strength-named')).toContainText('Primal');
    await expect(step.locator('.strength-named')).toContainText('Abyssal');
    await shot(step, 'built-screen2-balance-5-5.png');

    // The second resonance holds more points than the feeling: 2 and 8. The main side is
    // Abyssal, the sentence says most strength comes from what she does to others, and the
    // plate is mostly the dark mass, which keeps its lit rim.
    saved = draftSaved(page);
    await step.locator('input[type="range"]').fill('8');
    expect((await saved).status()).toBe(200);
    await expect(step.locator('.strength-pts')).toHaveText(
      `${seed.feeling_name} 2 · ${seed.outward_name} 8`
    );
    await expect(step.locator('.strength-named')).toHaveText('Abyssal, with a Primal side');
    await expect(step.locator('.strength-said')).toHaveText(
      'Most of your strength comes from what you do to others.'
    );
    const darkMass = await plate(page);
    expect(
      darkMass.darkShare,
      `a mostly dark mass, saw ${JSON.stringify(darkMass)}`
    ).toBeGreaterThan(0.5);
    await expect(step.locator('[data-layer="rim"]')).toBeVisible();
    const rimOpacity = await step
      .locator('[data-layer="rim"]')
      .evaluate((element) => parseFloat(getComputedStyle(element).opacity));
    expect(rimOpacity, 'the dark mass keeps a lit rim').toBeGreaterThan(0);
    await shot(step, 'built-screen2-abyssal-main.png');

    // "Helping them" swaps the side: the Abyssal pick is let go in one write, the eight
    // Celestial resonances show with none pressed, and her pick of one makes 7 and 3.
    saved = draftSaved(page);
    await step.getByRole('button', { name: 'Helping them', exact: true }).click();
    expect((await saved).status()).toBe(200);
    await expect(step.getByRole('button', { name: 'Helping them', exact: true })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    for (const name of CELESTIAL_EIGHT) {
      await expect(card(outwards(page), name), `${name} is offered`).toBeVisible();
    }
    await expect(outwards(page).locator('[aria-pressed="true"]')).toHaveCount(0);
    await expect(step.locator('input[type="range"]')).toBeDisabled();
    saved = draftSaved(page);
    await card(outwards(page), 'Bene').click();
    expect((await saved).status()).toBe(200);
    await expect(step.locator('.strength-pts')).toHaveText(`${seed.feeling_name} 7 · Bene 3`);
    await expect(step.locator('.strength-named')).toHaveText('Primal, with a Celestial side');
    await expect(step.locator('.strength-said')).toHaveText(
      'Most of your strength comes from what you feel.'
    );
    await shot(step, 'built-screen2-celestial-side.png');

    // A5: "neither" drops the second pick and gives all ten points to the feeling.
    saved = draftSaved(page);
    await step.getByRole('button', { name: 'Neither', exact: true }).click();
    expect((await saved).status()).toBe(200);
    await expect(step.getByText(OUTWARD_QUESTION, { exact: true })).toHaveCount(0);
    await expect(step.locator('input[type="range"]')).toBeDisabled();
    await expect(step.locator('.strength-pts')).toHaveText(`${seed.feeling_name} 10`);
    await expect(step.locator('.strength-skipped')).toContainText(
      'All 10 points go to the feeling'
    );
    const skippedTop = await step
      .locator('.strength-skipped')
      .evaluate((element) => parseFloat(getComputedStyle(element).marginTop));
    expect(skippedTop).toBeCloseTo(0.6 * rootPx, 1);
    const only = (await savedDraft(page, seed)).draft_data.gift_resonance_weights ?? [];
    expect(only).toHaveLength(1);
    expect(only[0].weight).toBe(10);
    await shot(step, 'built-screen2-neither.png');

    // A8, second form: a second pick and no feeling. The draft cannot be completed, and the
    // contents rail gives the reason in the player's words.
    const outwardOnly = await page.request.patch(
      `/api/character-creation/drafts/${seed.draft_id}/`,
      {
        headers: { 'X-CSRFToken': await csrfToken(page) },
        data: {
          draft_data: {
            gift_resonance_weights: [
              {
                resonance_id: kept.find((pick) => pick.weight === 2)?.resonance_id ?? 0,
                weight: 10,
              },
            ],
          },
        },
      }
    );
    expect(outwardOnly.ok(), await outwardOnly.text()).toBe(true);
    const refused = await savedDraft(page, seed);
    expect(refused.stage_errors[GIFT_STAGE]).toEqual([NO_FEELING]);
    await page.reload();
    await expect(step).toBeVisible({ timeout: 20000 });
    await expect(page.locator('.toc-note').first()).toContainText(NO_FEELING);

    // A6: a colour set in admin is the colour drawn. Fera has none yet, so it draws grey.
    const staff = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const admin = await staff.newPage();
    await logIn(admin, seed.staff_username, seed.staff_password);
    const adminPage = `/admin/arxii/resonance/${seed.admin_feeling_id}/change/`;
    await admin.goto(adminPage);
    await expect(admin.locator('#id_color_hex')).toHaveAttribute('type', 'color');
    const fera = card(feelings(page), seed.admin_feeling_name);
    saved = draftSaved(page);
    await fera.click();
    expect((await saved).status()).toBe(200);
    // The pick completes a draft that held only a second pick; the step stays open.
    await expect(step).toBeVisible();
    await expect(fera).toHaveAttribute('aria-pressed', 'true');
    const before = await plate(page);
    expect(before.spread, `Fera starts grey, saw ${JSON.stringify(before)}`).toBeLessThan(25);

    await admin.goto(adminPage);
    await admin.locator('#id_color_hex').fill(ADMIN_COLOUR.toLowerCase());
    await admin.locator('input[name="_continue"]').click();
    await expect(admin.locator('.messagelist .success')).toBeVisible();
    await expect(admin.locator('#id_color_hex')).toHaveValue(ADMIN_COLOUR.toLowerCase());
    await shot(admin.locator('#content'), 'built-screen2-admin-colour.png');
    await staff.close();

    await page.reload();
    await openFinishedStep(page, `${seed.admin_feeling_name}, ${seed.outward_name}`);
    await expect(card(feelings(page), seed.admin_feeling_name)).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    const swatch = await card(feelings(page), seed.admin_feeling_name)
      .locator('.strength-sw')
      .evaluate((element) => getComputedStyle(element).backgroundColor);
    expect(swatch).toBe('rgb(212, 66, 30)');
    const after = await plate(page);
    test
      .info()
      .annotations.push({ type: 'plate after admin colour', description: JSON.stringify(after) });
    expect(
      after.r,
      `the plate is ${ADMIN_COLOUR}'s red, saw ${JSON.stringify(after)}`
    ).toBeGreaterThan(after.g + 40);
    expect(after.r).toBeGreaterThan(after.b + 60);
    expect(after.spread).toBeGreaterThan(60);
    await shot(step.locator('.strength-plate'), 'built-screen2-plate-admin-colour.png');
  });

  test('casting: the picker, a cast worked in the usual resonance and one in the kindled one', async ({
    page,
    browser,
  }) => {
    const seed = readSeed();
    await logIn(page, ACCOUNT, PASSWORD);

    // Her corruption is not on any player page; staff read it from admin.
    const staff = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const admin = await staff.newPage();
    await logIn(admin, seed.staff_username, seed.staff_password);
    const corruption = async (rowId: number): Promise<number> => {
      await admin.goto(`/admin/arxii/characterresonance/${rowId}/change/`);
      return Number(await admin.locator('#id_corruption_current').inputValue());
    };
    const kindledBefore = await corruption(seed.kindled_row_id);
    const usualBefore = await corruption(seed.usual_row_id);

    const openCast = async () => {
      await page.goto(`/scenes/${seed.scene_id}`);
      await page.locator('button:has(svg.lucide-swords)').click();
      await page.getByRole('button', { name: 'Cast', exact: true }).click();
      const list = page.locator('#cast-section');
      await list
        .getByRole('button', { name: new RegExp(seed.technique_name) })
        .first()
        .click();
      await expect(page.getByTestId('cast-resonance-picker')).toBeVisible({ timeout: 15000 });
      return list;
    };

    // B1: the picker lists both resonances.
    let list = await openCast();
    const picker = page.getByTestId('cast-resonance-picker');
    const rows = picker.getByRole('button');
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0)).toContainText(seed.usual_name);
    await expect(rows.nth(0)).toContainText('your usual');
    await expect(rows.nth(0)).not.toContainText('Stronger');
    await expect(rows.nth(1)).toContainText(seed.kindled_name);
    await expect(rows.nth(1)).toContainText('Stronger here than');
    await expect(rows.nth(1)).toContainText('Kindled');
    await shot(list, 'built-screen4-picker.png');

    // B2: a cast worked in the usual resonance has no kindled line and no corruption.
    await page.getByRole('button', { name: new RegExp(`^Cast ${seed.technique_name}`) }).click();
    const primalResult = page.getByTestId('cast-ledger-result');
    await expect(primalResult).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId('power-ledger-panel')).toBeVisible();
    await expect(primalResult).not.toContainText('kindled cast power');
    await expect(primalResult).not.toContainText(/strengthened the cast/i);
    const primalTotal = Number(await page.getByTestId('power-ledger-total').innerText());
    const primalText = await primalResult.innerText();
    await shot(primalResult, 'built-screen4-result-primal.png');
    expect(await corruption(seed.kindled_row_id)).toBe(kindledBefore);
    expect(await corruption(seed.usual_row_id)).toBe(usualBefore);

    // B3: the same cast worked in the kindled resonance: a kindled line of 9, corruption + 2.
    await page.getByRole('button', { name: 'Done', exact: true }).click();
    await page.waitForTimeout(6500); // the scene's anti-spam wait between two acts is 5 seconds
    list = await openCast();
    await page
      .getByTestId('cast-resonance-picker')
      .getByRole('button', { name: new RegExp(seed.kindled_name) })
      .click();
    await expect(
      page
        .getByTestId('cast-resonance-picker')
        .getByRole('button', { name: new RegExp(seed.kindled_name) })
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(rows.nth(0)).toHaveAttribute('aria-pressed', 'false');
    await expect(rows.nth(1)).toHaveAttribute('aria-pressed', 'true');
    await shot(list, 'built-screen4-picker-kindled-pressed.png');
    await page.getByRole('button', { name: new RegExp(`^Cast ${seed.technique_name}`) }).click();
    const abyssalResult = page.getByTestId('cast-ledger-result');
    await expect(abyssalResult).toBeVisible({ timeout: 20000 });
    const kindledLine = abyssalResult.getByTestId('power-ledger-row-term').filter({
      hasText: 'kindled cast power',
    });
    await expect(kindledLine).toBeVisible();
    await expect(kindledLine).toContainText('+9');
    // The result says so in words, above the power ledger.
    const strengthened = abyssalResult.getByText(
      `Your kindled ${seed.kindled_name} strengthened the cast.`,
      { exact: true }
    );
    await expect(strengthened).toBeVisible();
    const sentenceBox = await strengthened.boundingBox();
    const ledgerBox = await page.getByTestId('power-ledger-panel').boundingBox();
    expect(sentenceBox && ledgerBox && sentenceBox.y < ledgerBox.y).toBe(true);
    const abyssalTotal = Number(await page.getByTestId('power-ledger-total').innerText());
    const abyssalText = await abyssalResult.innerText();
    await shot(abyssalResult, 'built-screen4-result-abyssal.png');
    expect(await corruption(seed.kindled_row_id)).toBe(kindledBefore + 2);
    expect(await corruption(seed.usual_row_id)).toBe(usualBefore);
    await staff.close();

    // A cast pays nothing (#5327): it is written down as an act her player may point a mark at,
    // with the kindled resonance suggested, and no "You earned" line reaches her messages.
    const acts = await page.request.get(
      `/api/magic/recorded-acts/?character_sheet=${seed.caster_id}`
    );
    expect(acts.ok()).toBe(true);
    const recorded = (
      (await acts.json()) as {
        results: { label: string; suggestions: { resonance_name: string }[] }[];
      }
    ).results.filter((act) => act.label.startsWith(seed.technique_name));
    expect(recorded, 'the two casts are each written down as an act').toHaveLength(2);
    for (const act of recorded) {
      expect(act.suggestions.map((row) => row.resonance_name)).toContain(seed.kindled_name);
    }
    const mine = await page.request.get('/api/roster/entries/mine/');
    expect(mine.ok()).toBe(true);
    const entry = ((await mine.json()) as { id: number; name: string }[]).find(
      (row) => row.name === STRENGTH_CASTER
    );
    expect(entry, `${STRENGTH_CASTER} is one of the account's characters`).toBeTruthy();
    await page.goto(`/characters/${entry!.id}`);
    await page.getByRole('button', { name: 'Growth', exact: true }).click();
    await expect(page.locator('#messages').getByText(/You earned/)).toHaveCount(0);

    // B4: the two results differ plainly on the page.
    expect(abyssalText).not.toEqual(primalText);
    test.info().annotations.push({
      type: 'power totals, usual then kindled',
      description: `${primalTotal} then ${abyssalTotal}`,
    });
    expect(abyssalTotal).toBeGreaterThan(primalTotal);
    expect(abyssalTotal - primalTotal).toBe(9);
  });
  test('staff fields: the other five numbers are on their admin forms with the values the seed set', async ({
    browser,
  }) => {
    const seed = readSeed();
    const staff = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const admin = await staff.newPage();
    await logIn(admin, seed.staff_username, seed.staff_password);

    /** Scroll a field to the middle of the window, so the picture shows it with its form. */
    const show = async (field: Locator) => {
      await field.evaluate((element) => element.scrollIntoView({ block: 'center' }));
      await expect(field).toBeInViewport();
    };

    // The Abyssal affinity's kindled boost, a percentage.
    await admin.goto(`/admin/arxii/affinity/${seed.abyssal_affinity_id}/change/`);
    const boost = admin.locator('#id_kindled_boost_percent');
    await expect(boost).toHaveValue('150');
    await show(boost);
    await shotPage(admin, 'built-admin-affinity-kindled-boost.png');

    // The strength row called Blazing, in the kindling configuration: its cast power.
    await admin.goto(`/admin/arxii/kindlingconfig/${seed.kindling_config_id}/change/`);
    const rowNames = await admin
      .locator('input[name$="-name"]')
      .evaluateAll((inputs) =>
        inputs.map((input) => [input.getAttribute('name'), (input as HTMLInputElement).value])
      );
    const blazing = rowNames.find(([, value]) => value === 'Blazing');
    expect(blazing, 'the Blazing strength row is on the page').toBeTruthy();
    const prefix = (blazing as string[])[0].replace(/-name$/, '');
    const castPower = admin.locator(`[name="${prefix}-cast_power"]`);
    await expect(castPower).toHaveValue('6');
    await show(castPower);
    await shotPage(admin, 'built-admin-kindled-cast-power.png');

    // The corruption configuration: the light part and where the full part starts.
    await admin.goto(`/admin/arxii/corruptionconfig/${seed.corruption_config_id}/change/`);
    const light = admin.locator('#id_light_corruption_percent');
    const full = admin.locator('#id_full_corruption_from_share');
    await expect(light).toHaveValue('10');
    await expect(full).toHaveValue('50');
    await show(light);
    await expect(full).toBeInViewport();
    await shotPage(admin, 'built-admin-corruption-config.png');

    // The drift configuration: the own-side range.
    await admin.goto(`/admin/arxii/driftconfig/${seed.drift_config_id}/change/`);
    const ownSide = admin.locator('#id_own_side_tolerance_percent');
    await expect(ownSide).toHaveValue('15');
    await show(ownSide);
    await shotPage(admin, 'built-admin-drift-config.png');
    await staff.close();
  });

  test('reduced motion: the aura holds still under it and moves without it', async ({
    browser,
  }) => {
    const seed = readSeed();

    /** The plate's drawn pixels reduced to one number, so two looks can be compared. */
    const sample = (page: Page) =>
      page.locator('.strength-aura canvas').evaluate((canvas: HTMLCanvasElement) => {
        const context = canvas.getContext('2d') as CanvasRenderingContext2D;
        const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
        let hash = 0;
        for (let i = 0; i < data.length; i += 1) hash = (hash * 31 + data[i]) | 0;
        return hash;
      });

    const look = async (reducedMotion: 'reduce' | 'no-preference') => {
      const context = await browser.newContext({
        viewport: { width: 1280, height: 900 },
        reducedMotion,
      });
      const page = await context.newPage();
      await logIn(page, ACCOUNT, PASSWORD);
      // Two picks, so the mass has two colours to swirl.
      const listed = await page.request.get('/api/magic/resonances/');
      const ids = new Map(
        ((await listed.json()) as { id: number; name: string }[]).map((row) => [row.name, row.id])
      );
      const saved = await page.request.patch(`/api/character-creation/drafts/${seed.draft_id}/`, {
        headers: { 'X-CSRFToken': await csrfToken(page) },
        data: {
          draft_data: {
            gift_resonance_weights: [
              { resonance_id: ids.get(seed.feeling_name), weight: 7 },
              { resonance_id: ids.get(seed.outward_name), weight: 3 },
            ],
          },
        },
      });
      expect(saved.ok(), await saved.text()).toBe(true);
      await page.goto('/characters/create');
      await openFinishedStep(page, `${seed.feeling_name}, ${seed.outward_name}`);
      await expect(page.locator('.strength-aura canvas')).toBeVisible();
      await page.waitForTimeout(500);
      const first = await sample(page);
      await page.waitForTimeout(1000);
      const second = await sample(page);
      await context.close();
      return { first, second };
    };

    const still = await look('reduce');
    test.info().annotations.push({
      type: 'reduced motion, two samples a second apart',
      description: `${still.first} and ${still.second}`,
    });
    expect(still.second).toBe(still.first);

    const moving = await look('no-preference');
    test.info().annotations.push({
      type: 'no preference, two samples a second apart',
      description: `${moving.first} and ${moving.second}`,
    });
    expect(moving.second).not.toBe(moving.first);
  });

  test('the fight: the picker offers both resonances and the declared action keeps the pick', async ({
    page,
    browser,
  }) => {
    const seed = readFightSeed();
    await logIn(page, FIGHT_ACCOUNT, PASSWORD);
    await page.goto('/game');
    await page
      .locator(
        `button[title="Connect as ${seed.character_name}"], ` +
          `button[title="Switch to ${seed.character_name}"], ` +
          `button[title="${seed.character_name}"], button:has-text("${seed.character_name}")`
      )
      .first()
      .click();
    await page
      .getByRole('navigation', { name: 'Sidebar modes' })
      .getByRole('button', { name: 'Combat', exact: true })
      .click({ timeout: 30000 });

    // Her turn: choose the technique as her cast.
    const turn = page.getByTestId('your-turn-section');
    await expect(turn).toBeVisible({ timeout: 30000 });
    // The technique is listed in the focused card first, then in each passive slot.
    await turn.getByRole('button', { name: seed.technique_name }).first().click();
    const target = turn.getByTestId('combatant-target-picker');
    if (await target.isVisible()) {
      await target.getByRole('button', { name: new RegExp(seed.opponent_name) }).click();
    }

    // The picker lists her usual resonance and the kindled Abyssal one, marked stronger.
    const picker = turn.getByTestId('cast-resonance-picker');
    await expect(picker).toBeVisible({ timeout: 15000 });
    const rows = picker.getByRole('button');
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0)).toContainText(seed.usual_name);
    await expect(rows.nth(0)).toContainText('your usual');
    await expect(rows.nth(0)).not.toContainText('Stronger');
    await expect(rows.nth(1)).toContainText(seed.kindled_name);
    await expect(rows.nth(1)).toContainText('Kindled');
    await expect(rows.nth(1)).toContainText('Stronger here than');

    // Press the Abyssal one and declare.
    await rows.nth(1).click();
    await expect(rows.nth(1)).toHaveAttribute('aria-pressed', 'true');
    await expect(rows.nth(0)).toHaveAttribute('aria-pressed', 'false');
    await shot(picker, 'built-screen4-fight-picker.png');
    await picker.scrollIntoViewIfNeeded();
    await shotPage(page, 'built-screen4-fight-panel.png');
    const declared = page.waitForResponse(
      (r) => r.url().includes('/dispatch/') && r.request().method() === 'POST'
    );
    await turn.getByTestId('submit-declarations-btn').click();
    expect((await declared).status()).toBe(200);

    // Her declared action holds that resonance: staff read it from the action's admin page.
    const staff = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const admin = await staff.newPage();
    await logIn(admin, seed.staff_username, seed.staff_password);
    await admin.goto(
      `/admin/arxii/combatroundaction/?participant__id__exact=${seed.participant_id}`
    );
    await admin.locator('#result_list tbody tr th a').first().click();
    // The admin page labels a resonance with its affinity: "Praedari (Abyssal)".
    await expect(admin.locator('#id_cast_resonance option[selected]')).toHaveText(
      new RegExp(`^${seed.kindled_name}\\b`)
    );
    await staff.close();
  });
});
