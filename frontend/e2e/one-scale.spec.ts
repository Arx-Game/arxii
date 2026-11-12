import { test, expect, type Page, type TestInfo } from '@playwright/test';

/**
 * Stats, skills and threads read on one scale (#5091), against a live server (no
 * mocked /api/**).
 *
 * Needs the rows `integration_tests.live_seeds.seed_one_scale_spec` writes for
 * e2e_test_account: the character "Odile Onescale" (level 3, strength 30, agility 20)
 * with a gift thread at level 30. Before #5091 the sheet read strength 3 and the thread
 * read level 3. The creation step moves the account's draft to the Attributes stage, so
 * this spec runs after the specs that read that draft at another stage. Runs with
 * `--config e2e.backend.config.ts`; each test saves a full-page screenshot into its
 * output folder, which the real-test workflow uploads.
 */

const CHARACTER = 'Odile Onescale';

async function logIn(page: Page) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill('e2e_test_account');
  await page.getByPlaceholder('Password').fill('TestPass123!');
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

async function shoot(page: Page, testInfo: TestInfo, name: string) {
  await page.screenshot({ path: testInfo.outputPath(name), fullPage: true });
}

async function rosterEntryId(page: Page): Promise<number> {
  const entries = await page.request.get('/api/roster/entries/mine/');
  expect(entries.ok()).toBe(true);
  const mine = (await entries.json()) as { id: number; name: string }[];
  const entry = mine.find((row) => row.name === CHARACTER);
  expect(entry, `${CHARACTER} is one of the account's characters`).toBeTruthy();
  return entry!.id;
}

async function csrf(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  return cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? '';
}

test.describe('one scale: the stored value everywhere', () => {
  test('the character sheet shows stats at their stored value', async ({ page }, testInfo) => {
    await logIn(page);
    await page.goto(`/characters/${await rosterEntryId(page)}`);
    const grid = page.getByTestId('stats-grid');
    await expect(grid).toBeVisible({ timeout: 15000 });
    await expect(grid).toContainText(/strength\s*30/i);
    await expect(grid).toContainText(/agility\s*20/i);
    await grid.scrollIntoViewIfNeeded();
    await shoot(page, testInfo, 'sheet-stats.png');
  });

  test('the thread page shows the stored level and caps', async ({ page }, testInfo) => {
    await logIn(page);
    const threads = await page.request.get('/api/magic/threads/');
    expect(threads.ok()).toBe(true);
    const body = (await threads.json()) as
      { results: { id: number; level: number }[] } | { id: number; level: number }[];
    const rows = Array.isArray(body) ? body : body.results;
    const thread = rows.find((row) => row.level === 30);
    expect(thread, 'the seeded thread at level 30').toBeTruthy();
    await page.goto(`/threads/${thread!.id}`);
    const level = page.getByTestId('thread-stat-level');
    await expect(level).toBeVisible({ timeout: 15000 });
    await expect(level).toHaveText(/^\s*30\s*$/);
    await shoot(page, testInfo, 'thread-detail.png');
  });

  test('creation allocates stats from 10 to 50 in steps of 10', async ({ page }, testInfo) => {
    await logIn(page);
    const drafts = await page.request.get('/api/character-creation/drafts/');
    expect(drafts.ok()).toBe(true);
    const draftBody = (await drafts.json()) as { id: number }[] | { results: { id: number }[] };
    const draft = (Array.isArray(draftBody) ? draftBody : draftBody.results)[0];
    expect(draft, 'the account has a creation draft').toBeTruthy();
    const moved = await page.request.patch(`/api/character-creation/drafts/${draft.id}/`, {
      data: { current_stage: 7 },
      headers: { 'X-CSRFToken': await csrf(page) },
    });
    expect(moved.ok(), await moved.text()).toBe(true);

    await page.goto('/characters/create');
    const strength = page.locator('output[aria-labelledby="lbl-strength"]');
    await expect(strength).toBeVisible({ timeout: 15000 });
    await expect(strength).toHaveText('20');
    await expect(page.getByText('Twelve statistics, 10 to 50 each')).toBeVisible();
    await shoot(page, testInfo, 'cg-attributes-default.png');

    await page.getByRole('button', { name: 'Lower strength' }).click();
    await expect(strength).toHaveText('10');
    await page.getByRole('button', { name: 'Raise agility' }).click();
    const agility = page.locator('output[aria-labelledby="lbl-agility"]');
    await expect(agility).toHaveText('30');
    await shoot(page, testInfo, 'cg-attributes-moved.png');

    // What the page shows is what the server kept: a fresh read of the draft.
    const reread = await page.request.get(`/api/character-creation/drafts/${draft.id}/`);
    const saved = (await reread.json()) as { draft_data: { stats?: Record<string, number> } };
    expect(saved.draft_data.stats?.strength).toBe(10);
    expect(saved.draft_data.stats?.agility).toBe(30);

    // An old-scale value is refused, so nothing writes a dot back into the draft.
    const refused = await page.request.patch(`/api/character-creation/drafts/${draft.id}/`, {
      data: { draft_data: { ...saved.draft_data, stats: { ...saved.draft_data.stats, wits: 3 } } },
      headers: { 'X-CSRFToken': await csrf(page) },
    });
    expect(refused.status()).toBe(400);
    expect(await refused.text()).toContain('between 10 and 50, in steps of 10');
  });
});
