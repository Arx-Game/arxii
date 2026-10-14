import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Browser, type Page } from '@playwright/test';

/**
 * Evidence-challenge round 2 for #4354, against the server seeded for round 1. Not a CI
 * spec. Who can read the GM panel's data, and the creature template page after the
 * builder replaced its inlines.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const shot = (name: string) => path.join(REPO_ROOT, 'docs', 'reviews', '4354', 'round2', name);
const PASSWORD = 'TestPass123!';

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

async function csrf(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  return cookies.find((c) => c.name === 'csrftoken')?.value ?? '';
}

test('round2: only the scene GM gets the GM panel data or the morale control', async ({
  browser,
}) => {
  for (const user of ['gm4354', 'tamsin4354', 'oriel4354', 'gmb4354']) {
    const page = await signIn(browser, user);
    const detail = await (await page.request.get('/api/combat/1/')).json();
    const morale = await page.request.post('/api/combat/1/standoff-morale/', {
      data: { group_id: 1, direction: 'shake', reason: 'Test reason: access check' },
      headers: { 'X-CSRFToken': await csrf(page) },
    });
    console.log(
      `${user}: GET /api/combat/1/ gm_standoff=${detail.gm_standoff === null ? 'null' : 'present'}` +
        ` standoff=${detail.standoff === null ? 'null' : 'present'}` +
        ` standoff_summary=${detail.standoff_summary === null ? 'null' : 'present'}` +
        ` | POST standoff-morale -> ${morale.status()}`
    );
    if (user === 'gm4354') {
      expect(detail.gm_standoff).not.toBeNull();
      expect(morale.status()).toBe(200);
    } else {
      expect(detail.gm_standoff ?? null).toBeNull();
      expect(morale.status()).toBe(403);
    }
  }
});

test('round2: the creature template page links the builder and has no drive or rule inlines', async ({
  browser,
}) => {
  const page = await signIn(browser, 'staff4354');
  await page.goto('/admin/arxii/creaturetemplate/1/change/');
  await expect(page.getByRole('link', { name: 'Open the Standoff Profile Builder' })).toBeVisible();
  const inlineHeadings = await page.locator('.inline-group h2').allTextContents();
  console.log(`inline groups on the creature page: ${JSON.stringify(inlineHeadings)}`);
  expect(inlineHeadings.join(' ')).not.toMatch(/drive|faction|regard/i);
  await page.screenshot({ path: shot('r2-01-creature-page.png'), fullPage: true });
});
