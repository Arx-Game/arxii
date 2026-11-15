import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Route } from '@playwright/test';
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

    let held: Entry[] = [];
    let saves = 0;
    let saveAnswers = 0;
    let draftAnswersAfterSave = 0;
    // Registered after the fixture's catch-all, so these answer first.
    await page.route('**/api/**', async (route: Route) => {
      const url = new URL(route.request().url());
      const p = url.pathname;
      const method = route.request().method();
      if (p === `/api/character-creation/drafts/${DRAFT_ID}/beats/`) {
        await route.fulfill({ json: [BEAT] });
      } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/offers/`) {
        const chapter = url.searchParams.get('chapter');
        await route.fulfill({
          json: { offers: chapter === 'backgrounds' ? OFFERS : [], terms: [] },
        });
      } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/` && method === 'GET') {
        await route.fulfill({ json: held });
      } else if (p === '/api/character-creation/drafts/' && method === 'GET') {
        // The draft fetch: quick on the first load, slow once a save has been made, as
        // the heaviest request on the page is. It answers with the server's own sum.
        const afterSave = saves > 0;
        if (afterSave) await new Promise((resolve) => setTimeout(resolve, DRAFT_MS));
        const spent = held.reduce((sum, entry) => sum + entry.cost, 0);
        const body = {
          ...draft,
          cg_points_spent: spent,
          cg_points_remaining: 100 - spent,
          draft_data: { ...(draft.draft_data as object), distinctions: held },
        };
        if (afterSave) draftAnswersAfterSave += 1;
        await route.fulfill({ json: [body] });
      } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/sync/`) {
        const body = route.request().postDataJSON() as {
          distinctions: { id: number; rank: number; offer_id: number }[];
        };
        saves += 1;
        const mine: Entry[] = body.distinctions.map((row) => {
          const picked = OFFERS.find((o) => o.offer_id === row.offer_id)!;
          return {
            distinction_id: row.id,
            distinction_name: picked.name,
            distinction_slug: picked.name.toLowerCase().replace(/ /g, '-'),
            category_slug: 'background',
            rank: row.rank,
            cost: picked.cost_per_rank * row.rank,
            notes: '',
            offer_ids: [row.offer_id],
            sources: [BEAT.name],
            arrivals: ['choice'],
          };
        });
        await new Promise((resolve) => setTimeout(resolve, SAVE_MS));
        held = mine;
        saveAnswers += 1;
        await route.fulfill({ json: { distinctions: mine, stat_adjustments: [] } });
      } else {
        await route.fallback();
      }
    });
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
      await expect.poll(() => saveAnswers, { timeout: SAVE_MS + 3000 }).toBe(1);
      await page.waitForTimeout(1000);
      expect(draftAnswersAfterSave).toBe(0);
      // The row is there now and the totals still are not: the ledger disagrees with
      // itself until the draft fetch lands.
      expect(await rows()).toEqual(['Bookish−15']);
      expect(await totals()).toEqual(['Starting100', 'Spent0', 'Gained0', 'Remaining100']);
      await page.screenshot({ path: shot('old-build-total-behind-the-pick.png'), fullPage: true });
      await expect.poll(() => draftAnswersAfterSave, { timeout: DRAFT_MS + 3000 }).toBe(1);
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
    expect(saveAnswers).toBe(0);
    await page.waitForTimeout(500);
    await page.screenshot({
      path: shot('2-total-moved-before-the-save-answers.png'),
      fullPage: true,
    });

    // The save answers; the draft fetch behind it has not. The total stands.
    await expect(scrabble).toBeEnabled({ timeout: SAVE_MS + 3000 });
    expect(saveAnswers).toBe(1);
    await page.waitForTimeout(1000);
    expect(draftAnswersAfterSave).toBe(0);
    expect(await totals()).toEqual(['Starting100', 'Remaining85']);

    // A second card, one the world pays 10 for, while that draft fetch is still out.
    await scrabble.click();
    await expect.poll(totals, { timeout: 1000 }).toEqual(['Starting100', 'Remaining95']);
    expect(await rows()).toEqual(['Bookish−15', 'Hard scrabble+10']);
    expect(saveAnswers).toBe(1);
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
    await expect.poll(() => saveAnswers, { timeout: SAVE_MS + 3000 }).toBe(2);
    await expect.poll(() => draftAnswersAfterSave, { timeout: DRAFT_MS + 4000 }).toBeGreaterThan(0);
    await page.waitForTimeout(1000);
    clearInterval(watch);
    expect(new Set(seen)).toEqual(new Set(['Starting100 Remaining95']));
    expect(await totals()).toEqual(['Starting100', 'Remaining95']);
    await page.screenshot({ path: shot('4-confirmed-by-the-server.png'), fullPage: true });
    expect(errors).toEqual([]);
  });
});
