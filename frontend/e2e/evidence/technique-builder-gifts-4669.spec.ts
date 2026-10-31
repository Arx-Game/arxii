import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';

/**
 * Review evidence for #4669, against a live server (no mocked /api/**): the
 * bug was a fetch that read a paginated body as a list, which mocks hide.
 * The database holds 25 Gift rows (more than the default page of 20) and a
 * staff account, e2e_test_account: the real-testing skill's Form B database,
 * then `AccountDB.objects.filter(username='e2e_test_account').update(is_staff=True)`
 * and 25 `Gift.objects.create(name=...)` rows. On main's getGifts the builder
 * page crashed with "l.map is not a function".
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4669');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

test('the staff technique builder lists every Gift from the live endpoint', async ({ page }) => {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill('e2e_test_account');
  await page.getByPlaceholder('Password').fill('TestPass123!');
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });

  const giftsResponse = page.waitForResponse((r) => r.url().includes('/api/magic/gifts/'));
  await page.goto('/techniques/build');
  const body = await (await giftsResponse).json();
  // The endpoint really is paginated: an envelope, not a list.
  expect(Array.isArray(body)).toBe(false);
  expect(body.count).toBe(25);
  expect(body.results).toHaveLength(25);

  const trigger = page.locator('#tech-gift');
  await expect(trigger).toBeVisible({ timeout: 15000 });
  await page.screenshot({ path: shot('builder.png'), fullPage: true });

  await trigger.click();
  const options = page.getByRole('option');
  await expect(options).toHaveCount(25);
  await expect(page.getByRole('option', { name: 'RT Zephyr' })).toBeVisible();
  await page.screenshot({ path: shot('gift-picker-open.png') });
});
