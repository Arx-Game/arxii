import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Browser, type Page } from '@playwright/test';

/**
 * Review evidence round 2 for #4415 against a real server (rt_4415, seeded by
 * seed_4415b.py): the GM panel at arrival for a Hatred group whose provoking
 * rule matches nobody, a Predation group a suppressing rule keeps back, and a
 * Predation group whose rule has no effect. Not a CI spec: it needs that seeded
 * server on :4001.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4415b');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);
const IDS = JSON.parse(process.env.RT_IDS ?? '{}') as Record<string, number>;

async function signIn(browser: Browser, username: string): Promise<Page> {
  const context = await browser.newContext({ viewport: { width: 1500, height: 1100 } });
  const page = await context.newPage();
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill(username);
  await page.getByPlaceholder('Password').fill('TestPass123!');
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'));
  return page;
}

test('A: the GM panel at arrival reads each rule effect', async ({ browser }) => {
  test.setTimeout(120_000);
  const gm = await signIn(browser, 'gm4415');
  await gm.goto(`/scenes/${IDS.scene_a}`);
  await gm.getByTestId('rail-tab-gm').click();
  await expect(gm.getByTestId('gm-standoff-panel')).toBeVisible({ timeout: 20_000 });
  for (const [name, file] of [
    ['Old foes (test)', 'A1-old-foes-box.png'],
    ['Kept back (test)', 'A2-kept-back-box.png'],
    ['Plain rule (test)', 'A3-plain-rule-box.png'],
  ]) {
    const box = gm.getByTestId('gm-standoff-group').filter({ hasText: name });
    await expect(box).toBeVisible();
    console.log(`== ${name}: ${(await box.innerText()).replace(/\s+/g, ' ')}`);
    await box.screenshot({ path: shot(file) });
  }
  console.log(
    `== GM prompts: ${(await gm.getByTestId('gm-prompt-row').allInnerTexts()).join(' || ').replace(/\s+/g, ' ')}`
  );
  await gm.screenshot({ path: shot('A0-gm-arrival.png'), fullPage: true });
});
