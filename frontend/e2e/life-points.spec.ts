import { readFileSync } from 'node:fs';

import { test, expect, type Page } from '@playwright/test';

/**
 * The CG points beside the life move with a card click, and agree with the server
 * (#5141), against a live server (no mocked /api/**). Runs with
 * `--config e2e.backend.config.ts`.
 *
 * Needs the rows `integration_tests.live_seeds.seed_life_points_spec` writes for its own
 * account, e2e_life_points_account (the real-test workflow seeds it after the server
 * starts and writes the ids to the JSON file named by LIFE_POINTS_SEED): a creation
 * draft at Lineage whose beginning meets a childhood beat with two cards, one that costs
 * CG points and one the world pays for, and a youth beat with one card (#5160).
 *
 * The page works its total out before the server has answered, from prices the server
 * sent earlier. This is the check that the figure it shows is the figure the server
 * then holds. Each save is held in the browser for a few seconds before it is sent, so
 * "before the server has answered" is certain: the server has not been asked yet.
 */

const ACCOUNT = 'e2e_life_points_account';
const HOLD_MS = 4000;

interface Seed {
  draft_id: number;
  costly_card: string;
  costly_price: number;
  paying_card: string;
  paying_price: number;
  later_card: string;
}

interface Points {
  starting_budget: number;
  spent: number;
  remaining: number;
}

function readSeed(): Seed {
  return JSON.parse(
    readFileSync(process.env.LIFE_POINTS_SEED ?? '/tmp/life-points-seed.json', 'utf8')
  ) as Seed;
}

async function logIn(page: Page) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill(ACCOUNT);
  await page.getByPlaceholder('Password').fill('TestPass123!');
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

/** The draft's CG points as the server adds them up now. */
async function serverPoints(page: Page, seed: Seed): Promise<Points> {
  const res = await page.request.get(`/api/character-creation/drafts/${seed.draft_id}/cg-points/`);
  expect(res.ok(), await res.text()).toBe(true);
  return (await res.json()) as Points;
}

const isSave = (url: string) => /\/api\/distinctions\/drafts\/\d+\/distinctions\/sync\/$/.test(url);
const isDraftFetch = (url: string) => new URL(url).pathname === '/api/character-creation/drafts/';

test.describe('the CG points beside the life', () => {
  test('move with the click, and are what the server then holds', async ({ page }) => {
    // Two saves, each held HOLD_MS, each followed by the page's heaviest fetch, then a clear.
    test.setTimeout(120_000);
    const seed = readSeed();
    await logIn(page);
    await page.goto('/characters/create');

    const costly = page.getByRole('button', { name: new RegExp(`^${seed.costly_card}`) });
    const paying = page.getByRole('button', { name: new RegExp(`^${seed.paying_card}`) });
    await expect(costly).toBeVisible({ timeout: 20000 });
    await expect(paying).toBeVisible();
    // A second run on the same database starts from the same place: nothing picked.
    for (const card of [costly, paying]) {
      if ((await card.getAttribute('aria-pressed')) === 'true') {
        const cleared = page.waitForResponse((r) => isSave(r.url()));
        await card.click();
        expect((await cleared).status()).toBe(200);
        await expect(card).toHaveAttribute('aria-pressed', 'false');
      }
    }

    // The right-hand panel is the one every stage shows (#5148): its "CG points" row is
    // the page's total, and the life's choices are listed under it.
    const panel = page.getByRole('complementary', { name: 'Marginalia' });
    const ledger = panel.locator('section.ledger');
    const total = () =>
      panel.locator('.record-rail .row', { hasText: 'CG points' }).locator('dd').textContent();
    const start = await serverPoints(page, seed);
    const budget = start.starting_budget;
    const line = (remaining: number) => `${budget - remaining} of ${budget} spent`;
    await expect.poll(total).toBe(line(start.remaining));

    // From here every save waits in the browser before it is sent.
    let sent = 0;
    await page.route(
      (url) => isSave(url.toString()),
      async (route) => {
        await new Promise((resolve) => setTimeout(resolve, HOLD_MS));
        sent += 1;
        await route.continue();
      }
    );

    // The card that costs points.
    let saved = page.waitForResponse((r) => isSave(r.url()));
    let refetched = page.waitForResponse(
      (r) => sent === 1 && isDraftFetch(r.url()) && r.request().method() === 'GET'
    );
    await costly.click();
    const afterCostly = start.remaining - seed.costly_price;
    await expect.poll(total, { timeout: 1500 }).toBe(line(afterCostly));
    // The server has not been asked: the save is still waiting in the browser, and the
    // server's own sum is where it was.
    expect(sent).toBe(0);
    expect((await serverPoints(page, seed)).remaining).toBe(start.remaining);
    await expect(ledger.locator('.row')).toHaveText([new RegExp(`^${seed.costly_card}`)]);

    // The save lands. The server's sum is the figure the page was already showing.
    expect((await saved).status()).toBe(200);
    expect((await serverPoints(page, seed)).remaining).toBe(afterCostly);
    expect(await total()).toBe(line(afterCostly));
    // And it is still showing it once the page has fetched the draft again.
    expect((await refetched).status()).toBe(200);
    await expect.poll(total).toBe(line(afterCostly));
    await expect(
      page.getByText(`CG points: ${budget - afterCostly} of ${budget}`, { exact: true })
    ).toBeVisible();

    // The card the world pays for, on top of the first.
    saved = page.waitForResponse((r) => isSave(r.url()));
    refetched = page.waitForResponse(
      (r) => sent === 2 && isDraftFetch(r.url()) && r.request().method() === 'GET'
    );
    await expect(paying).toBeEnabled();
    await paying.click();
    const afterBoth = afterCostly + seed.paying_price;
    await expect.poll(total, { timeout: 1500 }).toBe(line(afterBoth));
    expect(sent).toBe(1);
    expect((await serverPoints(page, seed)).remaining).toBe(afterCostly);

    expect((await saved).status()).toBe(200);
    const end = await serverPoints(page, seed);
    expect(end.remaining).toBe(afterBoth);
    expect((await refetched).status()).toBe(200);
    await expect.poll(total).toBe(line(afterBoth));
    await expect(ledger.locator('.row')).toHaveCount(2);
    await expect(
      page.getByText(`CG points: ${end.spent} of ${budget}`, { exact: true })
    ).toBeVisible();

    // Restart: Clear All Choices (#5146) asks first. Cancel leaves the server's life as
    // it is; confirming empties it, and the page and the server agree again.
    const restart = page.getByRole('button', { name: 'Restart: Clear All Choices' });
    const dialog = page.getByRole('dialog');
    await restart.click();
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog).toBeHidden();
    expect((await serverPoints(page, seed)).remaining).toBe(afterBoth);
    await expect(ledger.locator('.row')).toHaveCount(2);

    await restart.click();
    const cleared = page.waitForResponse(
      (r) => new URL(r.url()).pathname.endsWith('/clear-life/') && r.request().method() === 'POST'
    );
    await dialog.getByRole('button', { name: 'Clear all choices' }).click();
    expect((await cleared).status()).toBe(200);
    expect((await serverPoints(page, seed)).remaining).toBe(start.remaining);
    await expect(ledger.locator('.row')).toHaveCount(0);
    await expect.poll(total).toBe(line(start.remaining));
    await expect(costly).toHaveAttribute('aria-pressed', 'false');
    await expect(paying).toHaveAttribute('aria-pressed', 'false');
  });

  test('the life opens with every fold open and holds no text box, and the Background written on Final Touches is kept by the server (#5160, #5178)', async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const seed = readSeed();
    await logIn(page);
    await page.goto('/characters/create');

    // Two life stages, one section in each, and nothing has been clicked: both stages
    // and both sections are open, and the later stage's card is on the page.
    const costly = page.getByRole('button', { name: new RegExp(`^${seed.costly_card}`) });
    const later = page.getByRole('button', { name: new RegExp(`^${seed.later_card}`) });
    await expect(costly).toBeVisible({ timeout: 20000 });
    await expect(later).toBeVisible();
    await expect(page.locator('.interview .stage-acc')).toHaveCount(2);
    await expect(page.locator('.interview .stage-acc[data-open="true"]')).toHaveCount(2);
    await expect(page.locator('.interview .sec')).toHaveCount(2);
    await expect(page.locator('.interview .sec[data-open="true"]')).toHaveCount(2);

    // The life page asks for no free text about the life (#5178): no box at the end of
    // a stage and none under the last stage.
    await expect(page.getByText('Background Notes')).toHaveCount(0);
    await expect(page.getByText(/Recent History/)).toHaveCount(0);
    await expect(page.locator('.interview .life textarea')).toHaveCount(0);

    // The Background is one box on Final Touches, with a placeholder saying where the
    // text goes.
    const stageLink = (name: string) =>
      page.locator('.interview .toc-list a').filter({ hasText: name });
    await stageLink('Final Touches').click();
    const box = page.locator('#background');
    await expect(box).toBeVisible({ timeout: 20000 });
    await expect(page.getByRole('heading', { name: 'Background', exact: true })).toBeVisible();
    await expect(box).toHaveAttribute(
      'placeholder',
      /^You can write an optional description .* listed as their Background on the character sheet\.$/
    );
    await expect(box).toHaveAttribute('maxlength', '4000');

    // Text typed in the box is sent when the stage is left, and the server keeps it: the
    // draft read straight from the server holds it, the Review stage quotes it, and the
    // box shows it after a reload.
    const draftUrl = `/api/character-creation/drafts/${seed.draft_id}/`;
    const savesBackground = (url: string, method: string, body: string | null, value: string) => {
      if (new URL(url).pathname !== draftUrl || method !== 'PATCH' || !body) return false;
      const sent = JSON.parse(body) as { draft_data?: { background?: string } };
      return sent.draft_data?.background === value;
    };
    const text = `Kept the ledgers for a season (${Date.now()}).\n\nThen the river took the shop.`;
    let saved = page.waitForResponse((r) =>
      savesBackground(r.url(), r.request().method(), r.request().postData(), text)
    );
    await box.fill(text);
    await stageLink('Review').click();
    expect((await saved).status()).toBe(200);
    const held = await page.request.get(draftUrl);
    expect(held.ok(), await held.text()).toBe(true);
    expect((await held.json()).draft_data.background).toBe(text);
    const quoted = page.locator('.interview .written').filter({ hasText: 'Background' });
    await expect(quoted.locator('blockquote span')).toHaveText(text, {
      timeout: 20000,
      useInnerText: true,
    });

    await page.reload();
    await stageLink('Final Touches').click();
    await expect(page.locator('#background')).toHaveValue(text, { timeout: 20000 });

    // A second run on the same database starts from the same place: the box emptied and
    // the draft back on the life page.
    saved = page.waitForResponse((r) =>
      savesBackground(r.url(), r.request().method(), r.request().postData(), '')
    );
    await page.locator('#background').fill('');
    await stageLink('Lineage').click();
    expect((await saved).status()).toBe(200);
    const after = await page.request.get(draftUrl);
    expect((await after.json()).draft_data.background).toBe('');
    await expect(costly).toBeVisible({ timeout: 20000 });
    // The life page starts expanded again: fold state is never saved.
    await expect(page.locator('.interview .sec[data-open="true"]')).toHaveCount(2);
  });
});
