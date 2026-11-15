import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';
import { BEGINNING, CRADLE, DRAFT_ID, mockCg } from './fixtures/cgLineage';

/**
 * Review evidence for #5141, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * Character creation at Lineage, the life page: the CG points beside the cards move
 * with the click, while the save is still in flight, and stand while the draft fetch
 * that follows the save is still out. `EVIDENCE_OLD_BUILD=1` runs the same walk against
 * the build before #5141 and expects what the owner reported: the total on the old
 * figure until that draft fetch lands.
 */
const here = path.dirname(fileURLToPath(import.meta.url));
const shot = (name: string) => path.join(here, '..', '..', 'test-results', 'cg-points-5141', name);

const BEAT = {
  beat_id: 1,
  name: 'How you were raised',
  prompt: 'What was the house you grew up in like?',
  life_stage: 'childhood',
  selection: 'any',
  taken: false,
  unknown: false,
  line: '',
  answer_offer_ids: [101, 102, 103],
  allowance: null,
  allowance_is_points: false,
};

const offer = (
  offerId: number,
  distinctionId: number,
  name: string,
  text: string,
  cost: number
) => ({
  offer_id: offerId,
  distinction_id: distinctionId,
  name,
  distinction_name: name,
  distinction_description: text,
  player_line: text,
  chapter: 'backgrounds',
  arrives_as: 'choice',
  opener_label: '',
  cost_per_rank: cost,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
  opener_key: `beat:${BEAT.beat_id}`,
  first_look: true,
  held: false,
  effect_line: '',
  taken_per_feature: false,
  opens_feature: false,
  requires_feature_opened: false,
  cg_max_rank: 0,
  group: '',
  asks_figure_name: false,
  effects: [],
});
const OFFERS = [
  offer(101, 1, 'Bookish', 'You were raised among books and little else.', 15),
  offer(102, 2, 'Hard scrabble', 'Nothing came easy, and you learned to make do.', -10),
  offer(103, 3, 'Well travelled', 'You had seen three kingdoms before you were ten.', 5),
];

interface Entry {
  distinction_id: number;
  distinction_name: string;
  distinction_slug: string;
  category_slug: string;
  rank: number;
  cost: number;
  notes: string;
  offer_ids: number[];
  sources: string[];
  arrivals: string[];
}

const SAVE_MS = 3000;
const DRAFT_MS = 4000;

interface ServerOptions {
  /** What the server charges for a pick; the offer's own price unless given. */
  charge?: (offerId: number, rank: number) => number;
  /** Points the server's own sum carries that no pick on the page accounts for. */
  serverExtra?: number;
  /** The save is refused. */
  refuse?: boolean;
  /** The offers each chapter answers with. */
  offers?: Record<string, ReturnType<typeof offer>[]>;
  /** The Glimpse tag catalog (the Gift stage). */
  glimpseTags?: unknown[];
}

/**
 * The server behind the page: the life's one beat, the offers, a save that takes
 * SAVE_MS and a draft fetch that takes DRAFT_MS once a save has been made. Registered
 * after the fixture's catch-all, so these routes answer first.
 */
async function slowServer(page: Page, draft: { draft_data: unknown }, options: ServerOptions) {
  const offersByChapter = options.offers ?? { backgrounds: OFFERS };
  const all = Object.values(offersByChapter).flat();
  const state = { held: [] as Entry[], saves: 0, saveAnswers: 0, draftAnswersAfterSave: 0 };
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();
    if (p === `/api/character-creation/drafts/${DRAFT_ID}/beats/`) {
      await route.fulfill({ json: [BEAT] });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/offers/`) {
      const chapter = url.searchParams.get('chapter') ?? '';
      await route.fulfill({ json: { offers: offersByChapter[chapter] ?? [], terms: [] } });
    } else if (p === '/api/character-creation/glimpse-tags/') {
      await route.fulfill({ json: options.glimpseTags ?? [] });
    } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/` && method === 'GET') {
      await route.fulfill({ json: state.held });
    } else if (p === '/api/character-creation/drafts/' && method === 'GET') {
      // The draft fetch: quick on the first load, slow once a save has been made, as
      // the heaviest request on the page is. It answers with the server's own sum.
      const afterSave = state.saves > 0;
      if (afterSave) await new Promise((resolve) => setTimeout(resolve, DRAFT_MS));
      const picks = state.held.reduce((sum, entry) => sum + entry.cost, 0);
      const spent = picks + (state.held.length > 0 ? (options.serverExtra ?? 0) : 0);
      const body = {
        ...draft,
        cg_points_spent: spent,
        cg_points_remaining: 100 - spent,
        draft_data: { ...(draft.draft_data as object), distinctions: state.held },
      };
      if (afterSave) state.draftAnswersAfterSave += 1;
      await route.fulfill({ json: [body] });
    } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/sync/`) {
      const body = route.request().postDataJSON() as {
        distinctions: { id: number; rank: number; offer_id: number }[];
      };
      state.saves += 1;
      await new Promise((resolve) => setTimeout(resolve, SAVE_MS));
      if (options.refuse) {
        state.saveAnswers += 1;
        await route.fulfill({
          status: 400,
          json: { detail: 'At most one answer on How you were raised.' },
        });
        return;
      }
      const mine: Entry[] = body.distinctions.map((row) => {
        const picked = all.find((o) => o.offer_id === row.offer_id)!;
        return {
          distinction_id: row.id,
          distinction_name: picked.name,
          distinction_slug: picked.name.toLowerCase().replace(/ /g, '-'),
          category_slug: 'background',
          rank: row.rank,
          cost: options.charge
            ? options.charge(row.offer_id, row.rank)
            : picked.cost_per_rank * row.rank,
          notes: '',
          offer_ids: [row.offer_id],
          sources: [BEAT.name],
          arrivals: ['choice'],
        };
      });
      state.held = mine;
      state.saveAnswers += 1;
      await route.fulfill({ json: { distinctions: mine, stat_adjustments: [] } });
    } else {
      await route.fallback();
    }
  });
  return state;
}

test.describe('character creation: the CG points move with a card click (#5141)', () => {
  test('the total changes on the click and stands until the server confirms it', async ({
    page,
  }) => {
    const oldBuild = process.env.EVIDENCE_OLD_BUILD === '1';
    await page.setViewportSize({ width: 1280, height: 1100 });
    const draft = await mockCg(page, CRADLE);
    // The suggested life is already loaded for this beginning: nothing to load on mount.
    (draft.draft_data as Record<string, unknown>) = {
      life_loaded_for: BEGINNING.id,
      distinctions: [],
    };

    const server = await slowServer(page, draft, {});
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await page.goto('/characters/create');
    const bookish = page.getByRole('button', { name: /^Bookish/ });
    const scrabble = page.getByRole('button', { name: /^Hard scrabble/ });
    await expect(bookish).toBeVisible({ timeout: 15000 });
    const ledger = page.getByRole('complementary', { name: 'CG points' });
    const totals = () => ledger.locator('.tot').allTextContents();
    const rows = () => ledger.locator('.row').allTextContents();

    if (oldBuild) {
      expect(await totals()).toEqual(['Starting100', 'Spent0', 'Gained0', 'Remaining100']);
      await bookish.click();
      await expect(bookish).toHaveAttribute('aria-pressed', 'true', { timeout: 1000 });
      // The card is picked, the total is not: it still reads 100 a second after the
      // click, and still reads 100 when the save has answered.
      await page.waitForTimeout(1000);
      expect(await totals()).toEqual(['Starting100', 'Spent0', 'Gained0', 'Remaining100']);
      await expect.poll(() => server.saveAnswers, { timeout: SAVE_MS + 3000 }).toBe(1);
      await page.waitForTimeout(1000);
      expect(server.draftAnswersAfterSave).toBe(0);
      // The row is there now and the totals still are not: the ledger disagrees with
      // itself until the draft fetch lands.
      expect(await rows()).toEqual(['Bookish−15']);
      expect(await totals()).toEqual(['Starting100', 'Spent0', 'Gained0', 'Remaining100']);
      await page.screenshot({ path: shot('old-build-total-behind-the-pick.png'), fullPage: true });
      await expect.poll(() => server.draftAnswersAfterSave, { timeout: DRAFT_MS + 3000 }).toBe(1);
      await expect.poll(totals).toEqual(['Starting100', 'Spent15', 'Gained0', 'Remaining85']);
      return;
    }

    // Two totals: Starting and Remaining. No Spent or Gained line.
    expect(await totals()).toEqual(['Starting100', 'Remaining100']);
    await expect(ledger.getByText('Spent')).toHaveCount(0);
    await expect(ledger.getByText('Gained')).toHaveCount(0);
    await page.screenshot({ path: shot('1-before-any-pick.png'), fullPage: true });

    // A card that costs 15. The save takes three seconds; the total has moved well
    // inside one, with nothing answered.
    const clicked = Date.now();
    await bookish.click();
    await expect.poll(totals, { timeout: 1000 }).toEqual(['Starting100', 'Remaining85']);
    expect(Date.now() - clicked).toBeLessThan(1000);
    expect(await rows()).toEqual(['Bookish−15']);
    await expect(page.getByText('1 taken, 15 of 100 points spent')).toBeVisible();
    expect(server.saveAnswers).toBe(0);
    await page.waitForTimeout(500);
    await page.screenshot({
      path: shot('2-total-moved-before-the-save-answers.png'),
      fullPage: true,
    });

    // The save answers; the draft fetch behind it has not. The total stands.
    await expect(scrabble).toBeEnabled({ timeout: SAVE_MS + 3000 });
    expect(server.saveAnswers).toBe(1);
    await page.waitForTimeout(1000);
    expect(server.draftAnswersAfterSave).toBe(0);
    expect(await totals()).toEqual(['Starting100', 'Remaining85']);

    // A second card, one the world pays 10 for, while that draft fetch is still out.
    await scrabble.click();
    await expect.poll(totals, { timeout: 1000 }).toEqual(['Starting100', 'Remaining95']);
    expect(await rows()).toEqual(['Bookish−15', 'Hard scrabble+10']);
    expect(server.saveAnswers).toBe(1);
    await page.waitForTimeout(500);
    await page.screenshot({
      path: shot('3-second-pick-while-the-first-is-unconfirmed.png'),
      fullPage: true,
    });

    // Everything answers. The server's own sum is the same figure, and it never moved
    // off it in between.
    const seen: string[] = [];
    const watch = setInterval(() => {
      void totals()
        .then((t) => seen.push(t.join(' ')))
        .catch(() => {});
    }, 200);
    await expect.poll(() => server.saveAnswers, { timeout: SAVE_MS + 3000 }).toBe(2);
    await expect
      .poll(() => server.draftAnswersAfterSave, { timeout: DRAFT_MS + 4000 })
      .toBeGreaterThan(0);
    await page.waitForTimeout(1000);
    clearInterval(watch);
    expect(new Set(seen)).toEqual(new Set(['Starting100 Remaining95']));
    expect(await totals()).toEqual(['Starting100', 'Remaining95']);
    await page.screenshot({ path: shot('4-confirmed-by-the-server.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  /**
   * The page's own arithmetic is a forecast. Here the server charges 18 for the card its
   * offer prices at 15, and its own sum carries 2 more points that no pick on the page
   * accounts for. The total follows the server at each answer.
   */
  test("the server's figures replace the page's when they differ", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1100 });
    const draft = await mockCg(page, CRADLE);
    (draft.draft_data as Record<string, unknown>) = {
      life_loaded_for: BEGINNING.id,
      distinctions: [],
    };
    const server = await slowServer(page, draft, { charge: () => 18, serverExtra: 2 });

    await page.goto('/characters/create');
    const bookish = page.getByRole('button', { name: /^Bookish/ });
    await expect(bookish).toBeVisible({ timeout: 15000 });
    const ledger = page.getByRole('complementary', { name: 'CG points' });
    const totals = () => ledger.locator('.tot').allTextContents();

    await bookish.click();
    // The forecast, from the offer's price.
    await expect.poll(totals, { timeout: 1000 }).toEqual(['Starting100', 'Remaining85']);
    expect(server.saveAnswers).toBe(0);
    // The save answers with what it charged: 18.
    await expect.poll(() => server.saveAnswers, { timeout: SAVE_MS + 3000 }).toBe(1);
    await expect.poll(totals, { timeout: 1000 }).toEqual(['Starting100', 'Remaining82']);
    expect(server.draftAnswersAfterSave).toBe(0);
    await page.screenshot({ path: shot('5-the-save-charged-18.png'), fullPage: true });
    // The draft fetch lands with the server's own sum: 20.
    await expect.poll(() => server.draftAnswersAfterSave, { timeout: DRAFT_MS + 3000 }).toBe(1);
    await expect.poll(totals, { timeout: 1000 }).toEqual(['Starting100', 'Remaining80']);
    await page.screenshot({ path: shot('6-the-server-sum-is-20.png'), fullPage: true });
  });

  test('a refused save puts the old total back', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1100 });
    const draft = await mockCg(page, CRADLE);
    (draft.draft_data as Record<string, unknown>) = {
      life_loaded_for: BEGINNING.id,
      distinctions: [],
    };
    const server = await slowServer(page, draft, { refuse: true });

    await page.goto('/characters/create');
    const bookish = page.getByRole('button', { name: /^Bookish/ });
    await expect(bookish).toBeVisible({ timeout: 15000 });
    const ledger = page.getByRole('complementary', { name: 'CG points' });
    const totals = () => ledger.locator('.tot').allTextContents();

    await bookish.click();
    await expect.poll(totals, { timeout: 1000 }).toEqual(['Starting100', 'Remaining85']);
    expect(server.saveAnswers).toBe(0);
    // The server refuses. The card lets go, the row leaves, the total reads 100 again.
    await expect.poll(() => server.saveAnswers, { timeout: SAVE_MS + 3000 }).toBe(1);
    await expect.poll(totals, { timeout: 1000 }).toEqual(['Starting100', 'Remaining100']);
    await expect(bookish).toHaveAttribute('aria-pressed', 'false');
    expect(await ledger.locator('.row').allTextContents()).toEqual([]);
    await expect(page.getByText('0 taken, 0 of 100 points spent')).toBeVisible();
    await expect(page.getByText('That pick did not save. Try again.')).toBeVisible();
    await page.waitForTimeout(500);
    await page.screenshot({ path: shot('7-refused-save-total-back.png'), fullPage: true });
  });

  /**
   * The Gift stage prints the same figure in its rail ("CG points"), and its Glimpse
   * block offers cards of its own. A card clicked there moves that line at once too.
   */
  test("the Gift stage's CG points line moves with a card clicked there", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1100 });
    const draft = await mockCg(page, CRADLE);
    const GLIMPSE_OFFER = {
      ...offer(301, 31, 'Sees too much', 'You notice what people would rather you did not.', 5),
      chapter: 'glimpse',
      opener_key: 'tag:1',
    };
    (draft as unknown as { current_stage: number }).current_stage = 6;
    (draft.draft_data as Record<string, unknown>) = {
      life_loaded_for: BEGINNING.id,
      distinctions: [],
      glimpse_tag_ids: [1],
    };
    const server = await slowServer(page, draft, {
      offers: { glimpse: [GLIMPSE_OFFER] },
      glimpseTags: [
        {
          id: 1,
          axis: 'TONE',
          name: 'Dread',
          slug: 'dread',
          description: 'It came on like cold water.',
          example: '',
          sort_order: 1,
          offers: [
            {
              offer_id: 301,
              distinction_id: 31,
              name: 'Sees too much',
              player_line: GLIMPSE_OFFER.player_line,
              cost_per_rank: 5,
              max_rank: 1,
            },
          ],
        },
      ],
    });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await page.goto('/characters/create');
    const card = page.getByRole('button', { name: /^Sees too much/ });
    await expect(card).toBeVisible({ timeout: 15000 });
    const line = page.locator('.record-rail .row', { hasText: 'CG points' }).locator('dd');
    await expect(line).toHaveText('0 of 100 spent');

    await card.click();
    await expect(line).toHaveText('5 of 100 spent', { timeout: 1000 });
    expect(server.saveAnswers).toBe(0);
    await page.waitForTimeout(500);
    await page.screenshot({ path: shot('8-gift-line-moved-before-the-save-answers.png') });
    // It stands when the save has answered and the draft fetch has not.
    await expect.poll(() => server.saveAnswers, { timeout: SAVE_MS + 3000 }).toBe(1);
    await page.waitForTimeout(1000);
    expect(server.draftAnswersAfterSave).toBe(0);
    await expect(line).toHaveText('5 of 100 spent');
    expect(errors).toEqual([]);
  });
});
