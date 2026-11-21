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
 * Screenshots go to docs/reviews/5231/ under the repo root only with EVIDENCE_SHOTS=1.
 */

const ACCOUNT = 'e2e_strength_account';
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
  staff_username: string;
  staff_password: string;
}

interface Draft {
  draft_data: { gift_resonance_weights?: { resonance_id: number; weight: number }[] };
  stage_errors: Record<string, string[]>;
}

const PRIMAL_EIGHT = ['Arderi', 'Sereni', 'Audax', 'Medita', 'Fera', 'Civitas', 'Firma', 'Vola'];
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

function readSeed(): Seed {
  return JSON.parse(
    readFileSync(process.env.STRENGTH_SEED ?? '/tmp/strength-seed.json', 'utf8')
  ) as Seed;
}

const SHOT_DIR = join(process.cwd(), '..', 'docs', 'reviews', '5231');

/** A screenshot of `target`, kept only when EVIDENCE_SHOTS is set (CI writes none). */
async function shot(target: Locator, name: string) {
  if (!process.env.EVIDENCE_SHOTS) return;
  mkdirSync(SHOT_DIR, { recursive: true });
  await target.screenshot({ path: join(SHOT_DIR, name) });
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

test.describe.configure({ mode: 'serial' });

test.describe('what gives a character strength', () => {
  test.use({ viewport: { width: 1280, height: 900 } });

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
    await shot(step, 'built-screen1-empty.png');

    // A8, first form: nothing picked at all. The server's reason is recorded either way.
    const fresh = await savedDraft(page, seed);
    test.info().annotations.push({
      type: 'stage 6 errors, nothing picked',
      description: JSON.stringify(fresh.stage_errors[GIFT_STAGE]),
    });
    expect(fresh.draft_data.gift_resonance_weights ?? []).toEqual([]);
    expect((fresh.stage_errors[GIFT_STAGE] ?? []).length).toBeGreaterThan(0);

    // A2: exactly one feeling at a time.
    const arderi = card(feelings(page), seed.feeling_name);
    const audax = card(feelings(page), seed.second_feeling_name);
    let saved = draftSaved(page);
    await arderi.click();
    expect((await saved).status()).toBe(200);
    await expect(arderi).toHaveAttribute('aria-pressed', 'true');
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
    // The step stays open and readable after the pick.
    await expect(step).toBeVisible();
    const orange = await plate(page);
    expect(orange.r, `an orange plate, saw ${JSON.stringify(orange)}`).toBeGreaterThan(
      orange.b + 40
    );

    // A3: "hurting" shows the eight Abyssal resonances.
    const hurting = step.getByRole('button', { name: 'Hurting them', exact: true });
    saved = draftSaved(page);
    await hurting.click();
    expect((await saved).status()).toBe(200);
    await expect(hurting).toHaveAttribute('aria-pressed', 'true');
    await expect(step.getByText(OUTWARD_QUESTION, { exact: true })).toBeVisible();
    for (const name of ABYSSAL_EIGHT) {
      await expect(card(outwards(page), name), `${name} is offered`).toBeVisible();
    }
    const slider = step.locator('input[type="range"]');
    // Recorded as seen: whether the slider is on before the player picks an Abyssal card.
    test.info().annotations.push({
      type: 'slider enabled right after choosing hurting',
      description: String(await slider.isEnabled()),
    });
    test.info().annotations.push({
      type: 'abyssal cards pressed right after choosing hurting',
      description: String(await outwards(page).locator('[aria-pressed="true"]').count()),
    });
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
    await shot(step, 'built-screen2-balance-8-2.png');

    // A7: the server holds exactly the two weights, and a reload shows the same picks.
    const kept = (await savedDraft(page, seed)).draft_data.gift_resonance_weights ?? [];
    expect(kept).toHaveLength(2);
    expect(kept.map((pick) => pick.weight).sort((a, b) => b - a)).toEqual([8, 2]);
    await page.reload();
    await expect(step).toBeVisible({ timeout: 20000 });
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
                resonance_id: kept.find((pick) => pick.weight === 5)?.resonance_id ?? 0,
                weight: 10,
              },
            ],
          },
        },
      }
    );
    expect(outwardOnly.ok(), await outwardOnly.text()).toBe(true);
    const refused = await savedDraft(page, seed);
    expect(refused.stage_errors[GIFT_STAGE]).toEqual(['Pick the feeling that gives you strength.']);
    await page.reload();
    await expect(step).toBeVisible({ timeout: 20000 });
    await expect(page.locator('.toc-note').first()).toContainText(
      'Pick the feeling that gives you strength.'
    );

    // A6: a colour set in admin is the colour drawn. Fera has none yet, so it draws grey.
    const fera = card(feelings(page), seed.admin_feeling_name);
    saved = draftSaved(page);
    await fera.click();
    expect((await saved).status()).toBe(200);
    await expect(fera).toHaveAttribute('aria-pressed', 'true');
    const before = await plate(page);
    expect(before.spread, `Fera starts grey, saw ${JSON.stringify(before)}`).toBeLessThan(25);

    const staff = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const admin = await staff.newPage();
    await logIn(admin, seed.staff_username, seed.staff_password);
    await admin.goto(`/admin/arxii/resonance/${seed.admin_feeling_id}/change/`);
    const picker = admin.locator('#id_color_hex');
    await expect(picker).toHaveAttribute('type', 'color');
    await picker.fill(ADMIN_COLOUR.toLowerCase());
    await admin.locator('input[name="_continue"]').click();
    await expect(admin.locator('.messagelist .success')).toBeVisible();
    await expect(admin.locator('#id_color_hex')).toHaveValue(ADMIN_COLOUR.toLowerCase());
    await shot(admin.locator('#content'), 'built-screen2-admin-colour.png');
    await staff.close();

    await page.reload();
    await expect(step).toBeVisible({ timeout: 20000 });
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
    await page.getByRole('button', { name: new RegExp(`^Cast ${seed.technique_name}`) }).click();
    const abyssalResult = page.getByTestId('cast-ledger-result');
    await expect(abyssalResult).toBeVisible({ timeout: 20000 });
    const kindledLine = abyssalResult.getByTestId('power-ledger-row-flat_modifier').filter({
      hasText: 'kindled cast power',
    });
    await expect(kindledLine).toBeVisible();
    await expect(kindledLine).toContainText('+9');
    const abyssalTotal = Number(await page.getByTestId('power-ledger-total').innerText());
    const abyssalText = await abyssalResult.innerText();
    await shot(abyssalResult, 'built-screen4-result-abyssal.png');
    expect(await corruption(seed.kindled_row_id)).toBe(kindledBefore + 2);
    expect(await corruption(seed.usual_row_id)).toBe(usualBefore);
    await staff.close();

    // B4: the two results differ plainly on the page.
    expect(abyssalText).not.toEqual(primalText);
    test.info().annotations.push({
      type: 'power totals, usual then kindled',
      description: `${primalTotal} then ${abyssalTotal}`,
    });
    expect(abyssalTotal).toBeGreaterThan(primalTotal);
    expect(abyssalTotal - primalTotal).toBe(9);
  });
});
