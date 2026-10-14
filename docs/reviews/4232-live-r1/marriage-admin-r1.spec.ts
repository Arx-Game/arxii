import { test, expect, type Page } from '@playwright/test';
import path from 'node:path';

/**
 * #4232 evidence challenge round 1, item 3: the admin refusals, live on the head.
 * Expects a running server on :4001 whose database holds Rowan Ashby (node 1) married
 * to Lisbet Crane (node 2) with a birth recorded within that union (PHASE=refusals),
 * or the same with the birth removed (PHASE=delete).
 */
const SHOTS = path.join('..', 'docs', 'reviews', '4232-live-r1');
const USERNAME = 'e2e_test_account';
const PASSWORD = 'TestPass123!';
const PERSON_NODE = 1;
const PREFIX = 'Union_members';
const PHASE = process.env.PHASE ?? 'refusals';

async function login(page: Page, next: string): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="text"]').first().fill(USERNAME);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]', { hasText: /log in/i }).click();
  await expect(page).not.toHaveURL(/\/login(?:$|[?/#])/);
  await page.goto(next);
  await expect(page.locator('#content-main')).toBeVisible();
}

async function pickPartner(page: Page, rowIndex: number, name: string): Promise<void> {
  const row = page.locator(`#${PREFIX}-${rowIndex}`);
  await row.locator('.select2-selection').first().click();
  await page.locator('.select2-search__field').fill(name.split(' ')[0]);
  await page.locator('.select2-results__option', { hasText: name }).click();
}

test.describe('admin refusals, live (#4232 round 1)', () => {
  test.use({ viewport: { width: 1280, height: 900 } });
  test.setTimeout(90_000);

  test(`phase ${PHASE}`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    const changeUrl = `/admin/arxii/kinsperson/${PERSON_NODE}/change/`;
    await login(page, changeUrl);
    const group = page.locator(`#${PREFIX}-group`);
    await expect(group.locator(`#${PREFIX}-0`)).toContainText('Lisbet Crane');

    if (PHASE === 'refusals') {
      // Two new rows: the person as their own partner, and the spouse they already hold.
      await group.locator('.add-row a').click();
      await pickPartner(page, 1, 'Rowan Ashby');
      await group.locator('.add-row a').click();
      await pickPartner(page, 2, 'Lisbet Crane');
      await page.click('input[name="_continue"]');
      await expect(page.locator('.errornote')).toBeVisible();
      await expect(page.getByText('A person cannot marry themselves.')).toBeVisible();
      await expect(page.getByText('They already share an open marriage.')).toBeVisible();
      await page.locator(`#${PREFIX}-group`).scrollIntoViewIfNeeded();
      await page.locator(`#${PREFIX}-group`).screenshot({ path: path.join(SHOTS, 'admin-refuses-self-and-double-1280.png') });

      // Delete the married row while a birth depends on it: refused by name.
      await page.goto(changeUrl);
      await page.locator(`input[name="${PREFIX}-0-DELETE"]`).check();
      await page.click('input[name="_continue"]');
      await expect(page.locator('.errornote')).toBeVisible();
      await expect(page.getByText(/cannot be removed: a recorded birth depends on it/)).toBeVisible();
      await page.locator(`#${PREFIX}-group`).scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(SHOTS, 'admin-refuses-delete-with-birth-1280.png'), fullPage: false });
      return;
    }

    // PHASE delete: the birth is gone, so the row can be removed.
    await page.locator(`input[name="${PREFIX}-0-DELETE"]`).check();
    await page.click('input[name="_continue"]');
    await expect(page.locator('.messagelist .success')).toBeVisible();
    await expect(page.locator(`#${PREFIX}-0`)).toHaveCount(0);
    await page.locator(`#${PREFIX}-group`).scrollIntoViewIfNeeded();
    await page.locator(`#${PREFIX}-group`).screenshot({ path: path.join(SHOTS, 'admin-deleted-row-1280.png') });
  });
});
