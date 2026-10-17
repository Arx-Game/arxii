import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Browser, type Page } from '@playwright/test';

/**
 * Review evidence for #4415 against a real server (rt_4415, seeded by
 * seed_4415.py): Hunger, Hatred and Territory groups in one GM-run standoff,
 * seen by the GM, a player in the encounter and an onlooker in the scene; a
 * settled Orders group whose Calm hold lapses; the builder's cause effect and
 * the config preview rail. Not a CI spec: it needs that seeded server on
 * :4001. PART selects the phase (telnet steps run between parts).
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4415');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);
const PASSWORD = 'TestPass123!';
const IDS = JSON.parse(process.env.RT_IDS ?? '{}') as Record<string, number>;
const SCENE = () => `/scenes/${IDS.scene}`;
const CROWD = 'Quay crowd (test)';
const HOUNDS = 'Den hounds (test)';
const GRUDGE = 'Grudge-bearers (test)';

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

async function gmPanel(browser: Browser): Promise<Page> {
  const gm = await signIn(browser, 'gm4415');
  await gm.goto(SCENE());
  await gm.getByTestId('rail-tab-gm').click();
  await expect(gm.getByTestId('gm-standoff-panel')).toBeVisible({ timeout: 20_000 });
  return gm;
}

const gmGroup = (page: Page, name: string) =>
  page.getByTestId('gm-standoff-group').filter({ hasText: name });

async function logGroups(page: Page, label: string) {
  for (const name of [CROWD, HOUNDS, GRUDGE, 'Paid guards (test)']) {
    const box = gmGroup(page, name);
    if ((await box.count()) > 0) {
      console.log(`== ${label} | ${name}: ${(await box.first().innerText()).replace(/\s+/g, ' ')}`);
    }
  }
}

test.describe.configure({ mode: 'serial' });

test('part 1: arrival for the GM, a player and an onlooker; the GM shakes the haters', async ({
  browser,
}) => {
  test.skip(process.env.PART !== '1', 'part 1 only');
  test.setTimeout(240_000);
  const gm = await gmPanel(browser);
  await logGroups(gm, 'E1 GM');
  const prompt = gm.getByTestId('gm-prompt-row');
  console.log(`== E1 GM prompts: ${(await prompt.allInnerTexts()).join(' || ')}`);
  await gm.screenshot({ path: shot('01-gm-arrival.png'), fullPage: true });

  const pell = await signIn(browser, 'pell4415');
  await pell.goto(SCENE());
  await expect(pell.getByTestId('standoff-card')).toBeVisible({ timeout: 20_000 });
  for (const name of [CROWD, HOUNDS, GRUDGE]) {
    const row = pell.getByTestId('standoff-group').filter({ hasText: name });
    console.log(`== E1 Pell | ${name}: ${(await row.first().innerText()).replace(/\s+/g, ' ')}`);
  }
  console.log(
    `== E1 Pell page has Patience: ${await pell.getByText(/Patience:/).count()}, Hunger margin: ${await pell.getByText(/Hunger margin/).count()}, provokes: ${await pell.getByText(/provokes/).count()}`
  );
  await pell.screenshot({ path: shot('02-player-card.png'), fullPage: true });

  const anselm = await signIn(browser, 'anselm4415');
  await anselm.goto(SCENE());
  const summary = anselm.getByTestId('standoff-summary-card');
  await expect(summary).toBeVisible({ timeout: 20_000 });
  console.log(`== E1 Anselm summary: ${(await summary.innerText()).replace(/\s+/g, ' ')}`);
  console.log(
    `== E1 Anselm page has Patience: ${await anselm.getByText(/Patience:/).count()}, Hunger margin: ${await anselm.getByText(/Hunger margin/).count()}, provokes: ${await anselm.getByText(/provokes/).count()}, standoff-card: ${await anselm.getByTestId('standoff-card').count()}`
  );
  await anselm.screenshot({ path: shot('03-onlooker.png'), fullPage: true });

  // E2: shake the haters twice from the web panel; a reason is required.
  for (const step of ['falters', 'breaks']) {
    const box = gmGroup(gm, GRUDGE);
    await box.getByRole('button', { name: /^Shake$/ }).click();
    const confirm = gm.getByTestId('standoff-morale-confirm');
    await expect(confirm).toBeVisible();
    const go = confirm.getByRole('button', { name: /^Shake/ });
    console.log(`== E2 Shake button enabled before a reason: ${await go.isEnabled()}`);
    await confirm.getByRole('textbox').fill('PLACEHOLDER reason (test)');
    if (step === 'breaks')
      await gm.screenshot({ path: shot('04a-gm-shake-confirm.png'), fullPage: true });
    await go.click();
    await expect(gmGroup(gm, GRUDGE)).toContainText(step === 'falters' ? '(falter)' : '(break)', {
      timeout: 20_000,
    });
    // The GM page is not in the world (no live socket): reload to read the scene feed.
    await gm.reload();
    await expect(gm.getByText(`${GRUDGE} ${step}.`).first()).toBeVisible({ timeout: 20_000 });
    await gm.getByTestId('rail-tab-gm').click();
    await expect(gm.getByTestId('gm-standoff-panel')).toBeVisible({ timeout: 20_000 });
  }
  await gm.waitForTimeout(1500);
  await logGroups(gm, 'E2 GM after shakes');
  await gm.screenshot({ path: shot('04-gm-shake.png'), fullPage: true });
});

test('part 2: after the telnet hold; party action 1 seen by the GM', async ({ browser }) => {
  test.skip(process.env.PART !== '2', 'part 2 only');
  test.setTimeout(120_000);
  const gm = await gmPanel(browser);
  await logGroups(gm, 'E2/E3 GM');
  console.log(
    `== E3 GM page has losing patience: ${await gm.getByText(/losing patience/).count()}`
  );
  await gm.screenshot({ path: shot('04b-gm-after-hold-and-action-1.png'), fullPage: true });
});

test('part 3: Noble reads the hounds on the web (action 2)', async ({ browser }) => {
  test.skip(process.env.PART !== '3', 'part 3 only');
  test.setTimeout(180_000);
  const noble = await signIn(browser, 'noble4415');
  await noble.goto(SCENE());
  const hounds = noble.getByTestId('standoff-group').filter({ hasText: HOUNDS });
  await expect(hounds).toBeVisible({ timeout: 20_000 });
  await hounds.getByRole('button', { name: /Read them/ }).click();
  await noble.waitForTimeout(3000);
  await noble.reload();
  await expect(noble.getByText(/losing patience/).first()).toBeVisible({ timeout: 20_000 });
  await noble.screenshot({ path: shot('05a-noble-after-read.png'), fullPage: true });

  for (const user of ['gm4415', 'pell4415', 'anselm4415']) {
    const page = await signIn(browser, user);
    await page.goto(SCENE());
    const line = page.getByText(`The ${HOUNDS} are losing patience.`);
    await expect(line.first()).toBeVisible({ timeout: 20_000 });
    console.log(`== E4 ${user} sees the losing-patience line: ${await line.count()}`);
    if (user === 'anselm4415') {
      await page.screenshot({ path: shot('05-feed-losing-patience-onlooker.png'), fullPage: true });
    }
    if (user === 'pell4415') {
      await page.screenshot({ path: shot('05b-feed-losing-patience-player.png'), fullPage: true });
    }
    if (user === 'gm4415') {
      await page.screenshot({ path: shot('05c-feed-losing-patience-gm.png'), fullPage: true });
      await page.getByTestId('rail-tab-gm').click();
      await expect(page.getByTestId('gm-standoff-panel')).toBeVisible({ timeout: 20_000 });
      await logGroups(page, 'E4 GM');
      await page.screenshot({ path: shot('05d-gm-panel-after-action-2.png'), fullPage: true });
    }
  }
});

test('part 4: two proposals after action 3', async ({ browser }) => {
  test.skip(process.env.PART !== '4', 'part 4 only');
  test.setTimeout(120_000);
  const gm = await gmPanel(browser);
  await logGroups(gm, 'E5 GM');
  console.log(
    `== E5 GM prompts: ${(await gm.getByTestId('gm-prompt-row').allInnerTexts()).join(' || ')}`
  );
  await gm.screenshot({ path: shot('06-gm-two-proposals.png'), fullPage: true });
});

test('part 5: the paid guards leave when their Calm lapses', async ({ browser }) => {
  test.skip(process.env.PART !== '5', 'part 5 only');
  test.setTimeout(120_000);
  const gm = await signIn(browser, 'gm4415');
  await gm.goto(SCENE());
  await expect(gm.getByText('Paid guard 1 (test) leaves.').first()).toBeVisible({
    timeout: 20_000,
  });
  console.log(`== E6 guard 1 leaves: ${await gm.getByText('Paid guard 1 (test) leaves.').count()}`);
  console.log(`== E6 guard 2 leaves: ${await gm.getByText('Paid guard 2 (test) leaves.').count()}`);
  console.log(`== E6 run out lines: ${await gm.getByText(/Calm \(test\) on Paid guard/).count()}`);
  console.log(
    `== E6 GM prompts: ${(await gm.getByTestId('gm-prompt-row').allInnerTexts()).join(' || ')}`
  );
  await gm.screenshot({ path: shot('07-guards-leave.png'), fullPage: true });
  const anselm = await signIn(browser, 'anselm4415');
  await anselm.goto(SCENE());
  await expect(anselm.getByText('Paid guard 2 (test) leaves.').first()).toBeVisible({
    timeout: 20_000,
  });
  await anselm.screenshot({ path: shot('07b-guards-leave-onlooker.png'), fullPage: true });
});

test('part 6: the builder cause effect and the config preview rail', async ({ browser }) => {
  test.skip(process.env.PART !== '6', 'part 6 only');
  test.setTimeout(180_000);
  const staff = await signIn(browser, 'staff4415');
  await staff.goto(`/admin/_standoff_profile/${IDS.grudge}/`);
  const select = staff.locator('select[name$="cause_effect"]').first();
  await expect(select).toBeVisible({ timeout: 20_000 });
  console.log(`== E7 cause effect value: ${await select.inputValue()}`);
  console.log(
    `== E7 cause effect options: ${(await select.locator('option').allInnerTexts()).join(' | ')}`
  );
  const help = staff.getByText(/None, Suppress \(they will not start it against this character\)/);
  console.log(`== E7 help text count: ${await help.count()}`);
  if ((await help.count()) > 0) console.log(`== E7 help: ${await help.first().innerText()}`);
  const rail = staff.getByText(/They never fire on force/);
  console.log(`== E7 rail count: ${await rail.count()}`);
  if ((await rail.count()) > 0) console.log(`== E7 rail: ${await rail.first().innerText()}`);
  await staff.screenshot({ path: shot('08-builder-cause-effect.png'), fullPage: true });
  await select.selectOption('suppress');
  await staff.click('input[name="save_continue"]');
  await staff.waitForLoadState('load');
  await staff.goto(`/admin/_standoff_profile/${IDS.grudge}/`);
  console.log(
    `== E7 cause effect after save + reload: ${await staff.locator('select[name$="cause_effect"]').first().inputValue()}`
  );
  await staff.screenshot({ path: shot('08b-builder-after-save.png'), fullPage: true });

  await staff.goto('/admin/arxii/standoffconfig/1/change/');
  await expect(staff.locator('#id_hunger_margin_step')).toBeVisible({ timeout: 20_000 });
  const fieldsets = await staff.locator('fieldset h2').allInnerTexts();
  console.log(`== E7 fieldsets: ${fieldsets.join(' | ')}`);
  const causes = staff
    .locator('fieldset')
    .filter({ has: staff.locator('h2', { hasText: 'Causes' }) });
  console.log(`== E7 Causes fieldset: ${(await causes.innerText()).replace(/\s+/g, ' ')}`);
  const preview = staff.getByText(/A Hunger group with margin 0/);
  console.log(`== E7 preview: ${await preview.first().innerText()}`);
  console.log(
    `== E7 territory: ${await staff
      .getByText(/A Territory group/)
      .first()
      .innerText()}`
  );
  await staff.screenshot({ path: shot('09-config-preview.png'), fullPage: true });
  await staff.fill('#id_hunger_margin_step', '15');
  await staff.fill('#id_territory_patience', '4');
  await staff.click('input[name="_continue"]');
  await staff.waitForLoadState('load');
  await staff.goto('/admin/arxii/standoffconfig/1/change/');
  console.log(
    `== E7 after save: step ${await staff.locator('#id_hunger_margin_step').inputValue()}, patience ${await staff.locator('#id_territory_patience').inputValue()}`
  );
  console.log(
    `== E7 preview after: ${await staff
      .getByText(/A Hunger group with margin 0/)
      .first()
      .innerText()}`
  );
  console.log(
    `== E7 territory after: ${await staff
      .getByText(/A Territory group/)
      .first()
      .innerText()}`
  );
  await staff.screenshot({ path: shot('10-config-preview-after-save.png'), fullPage: true });
  await staff.fill('#id_hunger_margin_step', '10');
  await staff.fill('#id_territory_patience', '3');
  await staff.click('input[name="_continue"]');
  await staff.waitForLoadState('load');
  await staff.goto('/admin/arxii/standoffconfig/1/change/');
  console.log(
    `== E7 restored: step ${await staff.locator('#id_hunger_margin_step').inputValue()}, patience ${await staff.locator('#id_territory_patience').inputValue()}`
  );
});
