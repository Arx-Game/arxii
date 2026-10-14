import { test, expect, type Page } from '@playwright/test';
import path from 'node:path';

/** #4232 round 2: PHASE=add (a new person with one Spouses row) or PHASE=pact (delete refused, pact + birth). */
const SHOTS = path.join('..', 'docs', 'reviews', '4232-live-r2');
const USERNAME = 'e2e_test_account';
const PASSWORD = 'TestPass123!';
const PREFIX = 'Union_members';
const PHASE = process.env.PHASE ?? 'add';

async function login(page: Page, next: string): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="text"]').first().fill(USERNAME);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]', { hasText: /log in/i }).click();
  await expect(page).not.toHaveURL(/\/login(?:$|[?/#])/);
  await page.goto(next);
  await expect(page.locator('#content-main')).toBeVisible();
}

test.describe('admin add page and pact delete, live (#4232 round 2)', () => {
  test.use({ viewport: { width: 1280, height: 900 } });
  test.setTimeout(90_000);

  test(`phase ${PHASE}`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    if (PHASE === 'add') {
      await login(page, '/admin/arxii/kinsperson/add/');
      await page.fill('input[name="name"]', 'Ysolde Marrow');
      const group = page.locator(`#${PREFIX}-group`);
      await group.locator('.add-row a').click();
      const row = page.locator(`#${PREFIX}-0`);
      await row.locator('.select2-selection').first().click();
      await page.locator('.select2-search__field').fill('Orrin');
      await page.locator('.select2-results__option', { hasText: 'Father Orrin' }).click();
      await row.locator(`input[name="${PREFIX}-0-started_at"]`).fill('2026-10-14 03:00:00');
      await group.scrollIntoViewIfNeeded();
      await group.screenshot({ path: path.join(SHOTS, 'admin-add-page-new-person-with-spouse-1280.png') });
      await page.click('input[name="_continue"]');
      await expect(page.locator('.messagelist .success')).toBeVisible();
      await expect(page).toHaveURL(/\/admin\/arxii\/kinsperson\/\d+\/change\//);
      await expect(page.locator(`#${PREFIX}-0`)).toContainText('Father Orrin');
      await page.locator(`#${PREFIX}-group`).scrollIntoViewIfNeeded();
      await page.locator(`#${PREFIX}-group`).screenshot({ path: path.join(SHOTS, 'admin-add-page-saved-1280.png') });
      return;
    }
    await login(page, '/admin/arxii/kinsperson/1/change/');
    await expect(page.locator(`#${PREFIX}-0`)).toContainText('Lisbet Crane');
    await page.locator(`input[name="${PREFIX}-0-DELETE"]`).check();
    await page.click('input[name="_continue"]');
    await expect(page.locator('.errornote')).toBeVisible();
    await expect(page.getByText(/cannot be removed: a marriage pact and a recorded birth depends on it/)).toBeVisible();
    await page.locator(`#${PREFIX}-group`).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(SHOTS, 'admin-refuses-delete-with-pact-and-birth-1280.png'), fullPage: false });
  });
});
