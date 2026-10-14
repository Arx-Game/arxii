import { test, expect, type Page } from '@playwright/test';
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';

/**
 * #4232 LIVE evidence: nothing here is mocked. One Chromium context against a
 * running Evennia server on :4001 whose throwaway database holds one staff
 * account with one character, "Rowan Ashby" (Kinsperson node 1), and one
 * unsheeted node, "Lisbet Crane" (node 2), plus the "Marriage" UnionKind.
 *
 * Walks the spec's screens: the admin Kinsperson page's Spouses section (add a
 * row, set an end date), staff edit mode on the web sheet (no Marital status
 * row), and telnet `sheet` reading the derived status over the real telnet port.
 * Run with the backend config: `npx playwright test --config e2e.backend.config.ts e2e/marriage-live-4232.spec.ts`.
 * Throwaway: deleted from the branch after the run (real-testing skill, section 6).
 */

const SHOTS = path.join('..', 'docs', 'reviews', '4232-live');
const USERNAME = 'e2e_test_account';
const PASSWORD = 'TestPass123!';
const PERSON_NODE = 1;
const ENTRY_ID = 1;
const PREFIX = 'Union_members';

async function adminLogin(page: Page, next: string): Promise<void> {
  // The admin's own login redirects to the SPA login; the Django session it
  // sets is the one the admin reads.
  await page.goto('/login');
  await page.locator('input[type="text"]').first().fill(USERNAME);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]', { hasText: /log in/i }).click();
  await expect(page).not.toHaveURL(/\/login(?:$|[?/#])/);
  await page.goto(next);
  await expect(page.locator('#content-main')).toBeVisible();
}

/** Log in over the real telnet port and run `sheet`; returns the cleaned output. */
function telnetSheet(): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    const socket = net.createConnection({ host: 'localhost', port: 4000 });
    socket.on('data', (d) => chunks.push(d));
    socket.on('error', reject);
    const send = (line: string) => socket.write(`${line}\r\n`);
    setTimeout(() => send(`connect ${USERNAME} ${PASSWORD}`), 1500);
    setTimeout(() => send('sheet'), 4000);
    setTimeout(() => send('quit'), 7000);
    setTimeout(() => {
      socket.destroy();
      const raw = Buffer.concat(chunks).toString('latin1');
      // Strip telnet negotiation bytes and ANSI colour sequences.
      const text = raw
        .replace(/\xff[\xfb-\xfe]./g, '')
        .replace(/\xff\xfa[\s\S]*?\xff\xf0/g, '')
        .replace(/\x1b\[[0-9;]*m/g, '')
        .replace(/[^\x09\x0a\x0d\x20-\x7e]/g, '');
      resolve(text);
    }, 8500);
  });
}

test.describe('a marriage lives only in the kinship graph, live (#4232)', () => {
  test.use({ viewport: { width: 1280, height: 900 } });
  test.setTimeout(120_000);

  test('admin Spouses section, staff edit band, telnet sheet', async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    const changeUrl = `/admin/arxii/kinsperson/${PERSON_NODE}/change/`;
    await adminLogin(page, changeUrl);

    // Screen 2: the Kinsperson change page carries a Spouses section.
    const group = page.locator(`#${PREFIX}-group`);
    await expect(group).toBeVisible();
    await expect(group.locator('h2')).toHaveText(/Spouses/);
    await group.scrollIntoViewIfNeeded();
    await group.screenshot({ path: path.join(SHOTS, 'admin-spouses-empty-1280.png') });

    // Before any row: telnet reads Single.
    const single = await telnetSheet();
    fs.writeFileSync(path.join(SHOTS, 'telnet-sheet-before.txt'), single);
    expect(single).toContain('Marital Status: Single');

    // An empty row: the partner picker (admin autocomplete), the kind defaulted to
    // the wedlock kind, a start date.
    await group.locator('.add-row a').click();
    const row = page.locator(`#${PREFIX}-0`);
    await expect(row).toBeVisible();
    await expect(row.locator(`select[name="${PREFIX}-0-kind"]`)).toHaveValue('1');
    await row.locator('.select2-selection').first().click();
    await page.locator('.select2-search__field').fill('Lisbet');
    await page.locator('.select2-results__option', { hasText: 'Lisbet Crane' }).click();
    await row.locator(`input[name="${PREFIX}-0-started_at"]`).fill('2026-10-14 12:00:00');
    await group.screenshot({ path: path.join(SHOTS, 'admin-spouses-new-row-1280.png') });
    await page.click('input[name="_continue"]');

    // The saved row names the spouse, read back from the union's members.
    await expect(page.locator('.messagelist .success')).toBeVisible();
    const saved = page.locator(`#${PREFIX}-group`);
    await expect(saved.locator(`#${PREFIX}-0`)).toContainText('Lisbet Crane');
    await saved.scrollIntoViewIfNeeded();
    await saved.screenshot({ path: path.join(SHOTS, 'admin-spouses-saved-1280.png') });

    // Screen 4: telnet `sheet` reads Married from the union, no field anywhere.
    const married = await telnetSheet();
    fs.writeFileSync(path.join(SHOTS, 'telnet-sheet-married.txt'), married);
    expect(married).toContain('Marital Status: Married');

    // Screen 3: staff edit mode on the web sheet has no Marital status row.
    await page.goto(`/characters/${ENTRY_ID}`);
    await expect(page.getByText('Rowan Ashby').first()).toBeVisible({ timeout: 20_000 });
    await page.getByLabel('Edit').click();
    const band = page.getByText('Staff edit', { exact: true }).first();
    await expect(band).toBeVisible();
    await expect(page.getByText('Weight (pounds)').first()).toBeVisible();
    await expect(page.getByText('Vocation', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Marital status')).toHaveCount(0);
    await band.evaluate((el) => el.scrollIntoView({ block: 'start' }));
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(SHOTS, 'sheet-staff-edit-band-1280.png'), fullPage: false });

    // An end date on the row ends the marriage: telnet reads Divorced.
    await page.goto(changeUrl);
    await page.locator(`input[name="${PREFIX}-0-ended_at"]`).fill('2026-10-20 09:00:00');
    await page.click('input[name="_continue"]');
    await expect(page.locator('.messagelist .success')).toBeVisible();
    await page.locator(`#${PREFIX}-group`).scrollIntoViewIfNeeded();
    await page.locator(`#${PREFIX}-group`).screenshot({ path: path.join(SHOTS, 'admin-spouses-ended-1280.png') });
    const divorced = await telnetSheet();
    fs.writeFileSync(path.join(SHOTS, 'telnet-sheet-divorced.txt'), divorced);
    expect(divorced).toContain('Marital Status: Divorced');
  });
});
