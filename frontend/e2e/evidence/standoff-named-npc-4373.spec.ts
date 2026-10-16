import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Browser, type Page } from '@playwright/test';

/**
 * Review evidence for #4373 against a real server (rt_4373, seeded by
 * seed_4373.py): a GM stands a named NPC on a beat line, staff see the language
 * fields in the admin, then (after the beat runs) two players, the GM and an
 * onlooker each see their own seat of the named NPC group and the language gate.
 * Not a CI spec: it needs that seeded server on :4001. PART selects the phase.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4373');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);
const PASSWORD = 'TestPass123!';
const IDS = JSON.parse(process.env.RT_IDS ?? '{}') as Record<string, number>;
const MAUD = 'Maud Carrow (test)';
const NO_LANGUAGE = 'You share no language with them.';

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

test('part 1: the GM stands a named NPC; staff see the language fields', async ({ browser }) => {
  test.skip(process.env.PART !== '1', 'part 1 only');
  test.setTimeout(240_000);
  const gm = await signIn(browser, 'gm4373');
  await gm.goto(`/stories/author/${IDS.story}`);
  await gm.getByText('The Corle gate (test)').first().click();
  await gm.getByRole('button', { name: /Episode \(test\)/ }).click();
  await gm.getByRole('button', { name: 'Edit beat' }).first().click();
  await expect(gm.getByTestId('placement-panel-0')).toBeVisible({ timeout: 20_000 });
  await gm.getByRole('button', { name: 'Add opponent' }).click();
  await gm.getByTestId('beat-opponent-line-creature-2').selectOption({
    label: 'Gate Sellsword (test) (mook)',
  });
  const picker = gm.getByTestId('beat-opponent-line-persona-2');
  await expect(picker.getByRole('option', { name: MAUD })).toHaveCount(1);
  await picker.selectOption({ label: MAUD });
  await expect(gm.getByTestId('beat-opponent-line-count-2')).toBeDisabled();
  await expect(gm.getByTestId('placement-persona-2')).toContainText(
    `${MAUD} is a named NPC: their drives are their persona's properties`
  );
  await expect(gm.getByTestId('placement-summary-0')).toContainText(
    'speaks Riverland common (test)'
  );
  await gm.screenshot({ path: shot('01-gm-beat-dialog-named-npc.png'), fullPage: true });
  await gm.getByTestId('beat-opponent-line-row-2').screenshot({ path: shot('01b-line.png') });
  await gm.getByRole('button', { name: 'Save Beat' }).click();
  await expect(gm.getByRole('heading', { name: 'Edit Beat' })).toHaveCount(0, { timeout: 20_000 });
  // Read it back from the server: reopen the dialog on a fresh page.
  await gm.reload();
  await gm.getByText('The Corle gate (test)').first().click();
  await gm.getByRole('button', { name: /Episode \(test\)/ }).click();
  await gm.getByRole('button', { name: 'Edit beat' }).first().click();
  await expect(gm.getByTestId('placement-persona-2')).toBeVisible({ timeout: 20_000 });
  await gm
    .getByTestId('beat-opponent-line-row-2')
    .screenshot({ path: shot('01c-line-read-back.png') });

  const staff = await signIn(browser, 'staff4373');
  await staff.goto(`/admin/_standoff_profile/${IDS.template}/`);
  await expect(staff.getByText('Blank means no language')).toBeVisible();
  await expect(staff.getByText('spoken: needs Riverland common (test)')).toBeVisible();
  await staff.screenshot({ path: shot('02-profile-builder-language.png'), fullPage: true });
  await staff.goto('/admin/arxii/standoffapproach/');
  await expect(staff.getByRole('columnheader', { name: /Is verbal/ })).toBeVisible();
  await staff.screenshot({ path: shot('03-approach-list-is-verbal.png'), fullPage: true });
  await staff.getByRole('link', { name: 'Persuade (test)' }).click();
  await expect(
    staff.getByText('Refused against a group that shares no language with the actor.')
  ).toBeVisible();
  await staff.screenshot({ path: shot('03b-approach-change-form.png'), fullPage: true });
  await staff.goto(`/admin/arxii/beat/${IDS.beat}/change/`);
  await staff.getByRole('link', { name: 'Edit placement' }).last().click();
  await expect(staff.locator('#placement-root h1')).toContainText(MAUD);
  await expect(staff.getByText(`${MAUD} is a named NPC`)).toBeVisible();
  await expect(staff.getByText('Speaks Riverland common (test)')).toBeVisible();
  await staff.screenshot({ path: shot('04-placement-named-npc.png'), fullPage: true });
});

test('part 2: each seat of the named NPC group and the language gate', async ({ browser }) => {
  test.skip(process.env.PART !== '2', 'part 2 only');
  test.setTimeout(240_000);
  const scene = `/scenes/${IDS.scene}`;

  const wrenna = await signIn(browser, 'wrenna4373');
  await wrenna.goto(scene);
  await expect(wrenna.getByText(MAUD).first()).toBeVisible({ timeout: 20_000 });
  await expect(wrenna.getByText(`${MAUD}'s regard for you: harder`).first()).toBeVisible();
  await expect(wrenna.getByText('-300')).toHaveCount(0);
  // Wrenna speaks the sellswords' and Maud's language; only the language-less hound refuses her.
  await expect(
    wrenna.getByTestId('standoff-group').filter({ hasText: MAUD }).getByTestId('standoff-refusal')
  ).toHaveCount(0);
  await wrenna.screenshot({ path: shot('05-wrenna-card.png'), fullPage: true });

  const aubrin = await signIn(browser, 'aubrin4373');
  await aubrin.goto(scene);
  await expect(aubrin.getByText(MAUD).first()).toBeVisible({ timeout: 20_000 });
  await expect(aubrin.getByTestId('standoff-refusal').first()).toHaveText(NO_LANGUAGE);
  await expect(aubrin.getByRole('button', { name: /Persuade \(test\)/ }).first()).toBeDisabled();
  await expect(aubrin.getByRole('button', { name: /Show steel \(test\)/ }).first()).toBeEnabled();
  await expect(aubrin.getByText(/regard for you/)).toHaveCount(0);
  await aubrin.screenshot({ path: shot('06-aubrin-card-refused.png'), fullPage: true });

  // The regard moves the grade: the same non-verbal approach on Maud, Wrenna (disliked)
  // against Aubrin (no regard). Both have the same (empty) skills.
  const steel = (page: Page) =>
    page
      .getByTestId('standoff-group')
      .filter({ hasText: MAUD })
      .getByRole('button', { name: /Show steel \(test\)/ })
      .getByTestId('standoff-grade');
  const wrennaGrade = await steel(wrenna).innerText();
  const aubrinGrade = await steel(aubrin).innerText();
  console.log(`== Show steel on Maud: Wrenna ${wrennaGrade}, Aubrin ${aubrinGrade}`);
  // The grade buckets can saturate; the difficulty numbers are printed by the round 2 shell.
  await steel(wrenna)
    .locator('xpath=ancestor::button')
    .screenshot({ path: shot('05b-wrenna-steel-on-maud.png') });
  await steel(aubrin)
    .locator('xpath=ancestor::button')
    .screenshot({ path: shot('06b-aubrin-steel-on-maud.png') });

  const gm = await signIn(browser, 'gm4373');
  await gm.goto(scene);
  await gm.getByTestId('rail-tab-gm').click();
  const panel = gm.getByTestId('gm-standoff-panel');
  await expect(panel).toBeVisible({ timeout: 20_000 });
  const maudBox = gm.getByTestId('gm-standoff-group').filter({ hasText: MAUD });
  await expect(maudBox).toContainText('named NPC');
  await expect(maudBox).toContainText('Riverland common (test)');
  await expect(maudBox).toContainText('Wrenna: negative (-300)');
  await expect(maudBox).not.toContainText('Aubrin: neutral');
  await expect(maudBox).toContainText('Prudent (test), Major');
  await panel.screenshot({ path: shot('07-gm-panel-named-npc.png') });

  const anselm = await signIn(browser, 'anselm4373');
  await anselm.goto(scene);
  const summary = anselm.getByTestId('standoff-summary-card');
  await expect(summary).toBeVisible({ timeout: 20_000 });
  await expect(summary).toContainText(MAUD);
  await expect(summary).not.toContainText('Riverland');
  await expect(summary).not.toContainText('regard');
  await anselm.screenshot({ path: shot('08-onlooker-summary.png'), fullPage: true });
});

test('part 3: Wrenna presses the named NPC on the web; the room sees it', async ({ browser }) => {
  test.skip(process.env.PART !== '3', 'part 3 only');
  test.setTimeout(180_000);
  const scene = `/scenes/${IDS.scene}`;
  const wrenna = await signIn(browser, 'wrenna4373');
  await wrenna.goto(scene);
  const persuade = wrenna
    .getByTestId('standoff-group')
    .filter({ hasText: MAUD })
    .getByRole('button', { name: /Persuade \(test\)/ });
  await expect(persuade).toBeEnabled({ timeout: 20_000 });
  await persuade.click();
  // The press result comes back to the actor; the room line is read from the scene feed.
  await wrenna.waitForTimeout(3000);
  await wrenna.reload();
  await expect(
    wrenna.getByText(/Wrenna presses Maud Carrow \(test\) with Persuade/).first()
  ).toBeVisible({
    timeout: 20_000,
  });
  await wrenna.screenshot({ path: shot('09-wrenna-pressed-maud.png'), fullPage: true });
  const anselm = await signIn(browser, 'anselm4373');
  await anselm.goto(scene);
  await expect(anselm.getByText(/presses Maud Carrow \(test\) with Persuade/).first()).toBeVisible({
    timeout: 20_000,
  });
  await anselm.screenshot({ path: shot('10-onlooker-room-line.png'), fullPage: true });
});

async function postJson(page: Page, url: string, data: object) {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name === 'csrftoken')?.value ?? '';
  return page.request.post(url, { data, headers: { 'X-CSRFToken': csrf, Referer: page.url() } });
}

const HOUND = 'Hollow hound (test)';
const EXTRA = JSON.parse(process.env.RT_EXTRA ?? '{}') as Record<string, number>;

const steelOnMaud = (page: Page) =>
  page
    .getByTestId('standoff-group')
    .filter({ hasText: MAUD })
    .getByRole('button', { name: /Show steel \(test\)/ });

test('part 4: terms by gesture, adding named NPCs, and the dashboard', async ({ browser }) => {
  test.skip(process.env.PART !== '4', 'part 4 only');
  test.setTimeout(240_000);
  const scene = `/scenes/${IDS.scene}`;

  // R1: the hound has no language: verbal refused, terms by gesture allowed.
  const aubrin = await signIn(browser, 'aubrin4373');
  await aubrin.goto(scene);
  const hound = aubrin.getByTestId('standoff-group').filter({ hasText: HOUND });
  await expect(hound).toBeVisible({ timeout: 20_000 });
  await expect(hound.getByTestId('standoff-refusal').first()).toHaveText(
    'They have no language to answer in.'
  );
  const letUsPass = hound.getByRole('button', { name: /Let us pass \(test\)/ });
  await expect(letUsPass).toBeEnabled();
  console.log(
    `== Aubrin Show steel on Maud, no regard: ${await steelOnMaud(aubrin).getByTestId('standoff-grade').innerText()}`
  );
  await steelOnMaud(aubrin).screenshot({ path: shot('11-aubrin-steel-on-maud-no-regard.png') });
  await hound.screenshot({ path: shot('12-aubrin-hound-gesture-terms.png') });
  await letUsPass.click();
  await hound.getByRole('button', { name: /Spin for/ }).click();
  await aubrin.waitForTimeout(3000);
  await aubrin.reload();
  await expect(
    aubrin.getByText(/Aubrin names Let us pass \(test\) to the Hollow hound \(test\)/).first()
  ).toBeVisible({ timeout: 20_000 });
  await aubrin.screenshot({ path: shot('13-aubrin-named-terms-to-hound.png'), fullPage: true });

  // R2: the GM adds a named NPC the story uses through the Add Opponent dialog.
  const gm = await signIn(browser, 'gm4373');
  await gm.goto(scene);
  await gm.getByTestId('rail-tab-gm').click();
  await gm.getByTestId('add-opponent-trigger').click();
  const named = gm.getByTestId('add-opponent-named-npc');
  await expect(named.getByRole('option', { name: 'Ilse Varn (test)' })).toHaveCount(1);
  await expect(named.getByRole('option', { name: 'Stranger (test)' })).toHaveCount(0);
  await named.selectOption({ label: 'Ilse Varn (test)' });
  await gm.getByTestId('add-opponent-pool-select').click();
  await gm.getByRole('option', { name: 'Gate pool (test)' }).click();
  await gm.getByTestId('add-opponent-dialog').screenshot({ path: shot('14-gm-add-named-npc.png') });
  await gm.getByTestId('add-opponent-submit').click();
  await expect(gm.getByTestId('add-opponent-dialog')).toHaveCount(0, { timeout: 20_000 });
  await expect(gm.getByText('Ilse Varn (test)').first()).toBeVisible({ timeout: 20_000 });
  await gm.screenshot({ path: shot('15-gm-after-adding-ilse.png'), fullPage: true });

  // R3 (web API): a GM is refused a persona the story does not use; staff are allowed.
  const body = { tier: 'elite', threat_pool_id: EXTRA.pool, persona_id: EXTRA.stranger };
  const refused = await postJson(gm, `/api/combat/${EXTRA.encounter}/add_opponent/`, body);
  console.log(`== GM add Stranger: ${refused.status()} ${await refused.text()}`);
  expect(refused.status()).toBe(400);
  const staff = await signIn(browser, 'staff4373');
  await staff.goto(scene);
  const allowed = await postJson(staff, `/api/combat/${EXTRA.encounter}/add_opponent/`, body);
  console.log(`== staff add Stranger: ${allowed.status()}`);
  expect(allowed.status()).toBe(200);
  expect(await allowed.text()).toContain('Stranger (test)');

  // R5: the Required content panel lists the language-less standoff creature.
  await staff.goto('/admin/_ops/required-content/');
  await expect(staff.getByText('Standoff creature languages')).toBeVisible();
  await expect(staff.getByText('No language: Hollow hound (test).')).toBeVisible();
  await staff.screenshot({ path: shot('16-required-content-languages.png'), fullPage: true });
});

test('part 5: a favourable regard eases the grade', async ({ browser }) => {
  test.skip(process.env.PART !== '5', 'part 5 only');
  test.setTimeout(120_000);
  const aubrin = await signIn(browser, 'aubrin4373');
  await aubrin.goto(`/scenes/${IDS.scene}`);
  await expect(steelOnMaud(aubrin)).toBeVisible({ timeout: 20_000 });
  await expect(steelOnMaud(aubrin)).toContainText(`${MAUD}'s regard for you: easier`);
  console.log(
    `== Aubrin Show steel on Maud, regard +300: ${await steelOnMaud(aubrin).getByTestId('standoff-grade').innerText()}`
  );
  await steelOnMaud(aubrin).screenshot({ path: shot('17-aubrin-steel-on-maud-favoured.png') });
});
