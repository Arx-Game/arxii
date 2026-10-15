/* Scratch real-testing spec for #4362 (not committed). Runs against rtc_4362 on :4001. */
import { expect, test, type Page } from '@playwright/test';
import { writeFileSync } from 'node:fs';

const BASE = 'http://localhost:4001';
const OUT = '../docs/reviews/4362';
const YSMAY = 5;
const ORLA = 7;
const TOBIAH = 9;
const HOBB = 11;
// The sheet page is keyed by roster entry, not by character.
const YSMAY_ENTRY = 1;
const TOBIAH_ENTRY = 3;

async function login(page: Page, user: string, password: string) {
  await page.goto(`${BASE}/login`);
  await page.waitForLoadState('networkidle');
  await page.getByPlaceholder('Username or Email').fill(user);
  await page.getByPlaceholder('Password').fill(password);
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

async function csrf(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  return cookies.find((c) => c.name === 'csrftoken')?.value ?? '';
}

async function dispatch(page: Page, character: number, key: string, kwargs: object) {
  const res = await page.request.post(`${BASE}/api/actions/characters/${character}/dispatch/`, {
    headers: { 'X-CSRFToken': await csrf(page), Referer: BASE },
    data: { ref: { backend: 'registry', registry_key: key }, kwargs },
  });
  const body = await res.json();
  return { status: res.status(), body };
}

async function card(page: Page, sheet: number) {
  const res = await page.request.get(`${BASE}/api/worship/pledge-cards/?character_sheet=${sheet}`);
  return (await res.json()).results[0];
}

test.setTimeout(120_000);

test('A ysmay pledges on the web', async ({ page }) => {
  await login(page, 'e2e_test_account', 'TestPass123!');
  await page.goto(`${BASE}/characters/${YSMAY_ENTRY}`);
  await page.getByTestId('worship-section').waitFor();
  await page.getByTestId('worship-section').screenshot({ path: `${OUT}/01-sheet-before.png` });
  await page.getByTestId('pledge-button').click();
  await page.getByRole('combobox', { name: 'To' }).click();
  await page.getByRole('option', { name: 'Ombrin' }).click();
  await page.getByLabel(/\[staff-authored pledge name\]/).click();
  await page.getByLabel(/Prayer/).fill('[player-written prayer]');
  await page.getByRole('dialog').screenshot({ path: `${OUT}/02-pledge-dialog.png` });
  await page.getByRole('button', { name: 'Pledge', exact: true }).click();
  const toast = page.locator('[data-sonner-toast]').first();
  await toast.waitFor();
  writeFileSync(`${OUT}/a-toast.txt`, (await toast.innerText()) + '\n');
  writeFileSync(`${OUT}/a-card.json`, JSON.stringify(await card(page, YSMAY), null, 2));
});

test('B ysmay sacrifices, performs the rite and closes', async ({ page }) => {
  await login(page, 'e2e_test_account', 'TestPass123!');
  await page.goto(`${BASE}/characters/${YSMAY_ENTRY}`);
  await page.getByTestId('pledge-card').waitFor();
  await page.getByTestId('sacrifice-button').click();
  await page.getByRole('dialog').getByText('silk scarf').click();
  await page.getByRole('dialog').screenshot({ path: `${OUT}/04-sacrifice-dialog.png` });
  await page.getByRole('dialog').getByRole('button', { name: 'Sacrifice', exact: true }).click();
  const toast = page.locator('[data-sonner-toast]').first();
  await toast.waitFor();
  writeFileSync(`${OUT}/b-sacrifice-toast.txt`, (await toast.innerText()) + '\n');
  const rite = await dispatch(page, YSMAY, 'worship_rite', { rite_name: "Ombrin's rite" });
  writeFileSync(`${OUT}/b-rite.json`, JSON.stringify(rite, null, 2));
  await page.reload();
  await page.getByTestId('pledge-card').waitFor();
  await expect(page.getByTestId('close-pledge-button')).toBeVisible();
  await page.getByTestId('worship-section').screenshot({ path: `${OUT}/05-pledge-card-ready.png` });
  writeFileSync(`${OUT}/b-card-ready.json`, JSON.stringify(await card(page, YSMAY), null, 2));
  await page.getByTestId('close-pledge-button').click();
  const closed = page.locator('[data-sonner-toast]').first();
  await closed.waitFor();
  writeFileSync(`${OUT}/b-close-toast.txt`, (await closed.innerText()) + '\n');
  await page.reload();
  await page.getByTestId('pledge-card').waitFor();
  await page.getByTestId('worship-section').screenshot({ path: `${OUT}/06-pledge-card-closed.png` });
  writeFileSync(`${OUT}/b-card-closed.json`, JSON.stringify(await card(page, YSMAY), null, 2));
});

test('C room panel at the shrine', async ({ page }) => {
  await login(page, 'e2e_test_account', 'TestPass123!');
  await page.goto(`${BASE}/game`);
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: `${OUT}/07-game.png`, fullPage: false });
  const block = page.getByTestId('holy-site-block');
  await block.waitFor({ timeout: 30000 });
  await block.screenshot({ path: `${OUT}/08-holy-site-block.png` });
  writeFileSync(`${OUT}/c-holy-site.txt`, (await block.innerText()) + '\n');
});

test('D orla takes, closes too early and sacrifices', async ({ page }) => {
  await login(page, 'e2e_test_account', 'TestPass123!');
  const log: object[] = [];
  const step = async (label: string, character: number, key: string, kwargs: object) => {
    const r = await dispatch(page, character, key, kwargs);
    log.push({ label, ...r });
  };
  await step('orla takes', ORLA, 'pledge_take', { pledge: 1, prayer: '' });
  await step('orla closes too early', ORLA, 'pledge_close', {});
  await step('orla sacrifices the copper bowl', ORLA, 'sacrifice', { item_ids: [2] });
  log.push({ label: 'orla card', card: await card(page, ORLA) });
  writeFileSync(`${OUT}/d-orla.json`, JSON.stringify(log, null, 2));
});

test('E orla closes twice', async ({ page }) => {
  await login(page, 'e2e_test_account', 'TestPass123!');
  const log: object[] = [];
  for (const label of ['first close', 'second close']) {
    log.push({ label, ...(await dispatch(page, ORLA, 'pledge_close', {})) });
    log.push({ label: `${label} card`, card: await card(page, ORLA) });
  }
  writeFileSync(`${OUT}/e-orla-closes.json`, JSON.stringify(log, null, 2));
});

test('F lapse cards', async ({ page }) => {
  await login(page, 'e2e_test_account', 'TestPass123!');
  writeFileSync(
    `${OUT}/f-lapse-cards.json`,
    JSON.stringify({ tobiah: await card(page, TOBIAH), hobb: await card(page, HOBB) }, null, 2)
  );
  await page.goto(`${BASE}/characters/${TOBIAH_ENTRY}`);
  await page.getByTestId('pledge-card').waitFor();
  await page.getByTestId('worship-section').screenshot({ path: `${OUT}/09-tobiah-lapsed.png` });
});

test('G being service builder', async ({ page }) => {
  await login(page, 'staff_4362', 'StaffPass123!');
  await page.goto(`${BASE}/admin/_being_service/1/`);
  await page.screenshot({ path: `${OUT}/10-being-service-builder.png`, fullPage: true });
  await page.click('#add-pledge-btn');
  const last = page.locator('#pledges-body .bs-pledge').last();
  await last.locator('input[name$="-name"]').fill('[staff-authored second pledge name]');
  await last.locator('input[name$="-favor_target"]').fill('10');
  await last.locator('input[name$="-span_weeks"]').fill('1');
  const rite = last.locator('select[name$="-closing_rite"]');
  const value = await rite.locator('option', { hasText: "Ombrin's rite" }).first().getAttribute('value');
  await rite.selectOption(value ?? '');
  await page.click('input[name=save_continue]');
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: `${OUT}/11-being-service-saved.png`, fullPage: true });
  await page.goto(`${BASE}/admin/arxii/worshippedbeing/1/change/`);
  await page.locator('.object-tools').screenshot({ path: `${OUT}/12-being-change-object-tool.png` });
});

test('H builder duplicate name and required content', async ({ page }) => {
  await login(page, 'staff_4362', 'StaffPass123!');
  await page.goto(`${BASE}/admin/_being_service/1/`);
  await page.click('#add-pledge-btn');
  const last = page.locator('#pledges-body .bs-pledge').last();
  await last.locator('input[name$="-name"]').fill('[staff-authored pledge name]');
  await last.locator('input[name$="-favor_target"]').fill('10');
  await last.locator('input[name$="-span_weeks"]').fill('1');
  const rite = last.locator('select[name$="-closing_rite"]');
  const value = await rite.locator('option', { hasText: "Ombrin's rite" }).first().getAttribute('value');
  await rite.selectOption(value ?? '');
  await page.click('input[name=save_continue]');
  await page.waitForLoadState('networkidle');
  const errors = page.locator('.errorlist, .errornote');
  writeFileSync(`${OUT}/h-duplicate-errors.txt`, (await errors.allInnerTexts()).join('\n') + '\n');
  await page.locator('#pledges-body').screenshot({ path: `${OUT}/13-builder-duplicate-refused.png` });
  const row = async (file: string) => {
    await page.goto(`${BASE}/admin/_ops/`);
    const panel = page.getByText('Favor outcome awards: closing awards').first();
    await panel.waitFor({ timeout: 30000 });
    const item = panel.locator('xpath=ancestor::*[self::tr or self::li][1]');
    writeFileSync(`${OUT}/${file}.txt`, (await item.innerText()) + '\n');
    await item.screenshot({ path: `${OUT}/${file}.png` });
  };
  await row('14-required-content-present');
  writeFileSync(`${OUT}/h-ready-for-delete`, '');
  // The runner removes every CLOSING award row from rtc_4362 here, then touches h-deleted.
  const { existsSync } = await import('node:fs');
  for (let i = 0; i < 60 && !existsSync(`${OUT}/h-deleted`); i++) await page.waitForTimeout(1000);
  await row('15-required-content-flagged');
});

test('I required content fragment', async ({ page }) => {
  const tag = process.env.RC_TAG ?? 'x';
  await login(page, 'staff_4362', 'StaffPass123!');
  await page.goto(`${BASE}/admin/_ops/required-content/`);
  await page.waitForLoadState('networkidle');
  const html = await page.content();
  writeFileSync(`${OUT}/rc-${tag}.html`, html);
  const row = page.locator('tr, li').filter({ hasText: 'Favor outcome awards: closing awards' }).last();
  writeFileSync(`${OUT}/rc-${tag}.txt`, (await row.innerText()) + '\n');
  await row.screenshot({ path: `${OUT}/rc-${tag}.png` });
});
