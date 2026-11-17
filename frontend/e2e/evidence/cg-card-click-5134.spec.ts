import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Route } from '@playwright/test';
import { BEGINNING, CRADLE, DRAFT_ID, mockCg } from './fixtures/cgLineage';

/**
 * Review evidence for #5134, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * Character creation at Lineage, the life page's cards: a clicked card shows picked
 * at once, while the save behind it is still in flight, and after the save answers
 * the page asks for the draft's distinctions no second time (the save's own answer
 * is the list).
 */
const here = path.dirname(fileURLToPath(import.meta.url));
const shot = (name: string) => path.join(here, '..', '..', 'test-results', 'cg-cards-5134', name);

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

const SECOND_BEAT = {
  ...BEAT,
  beat_id: 2,
  name: 'What you were taught',
  prompt: 'What did they make sure you learned?',
  answer_offer_ids: [201, 202],
};

const offer = (
  offerId: number,
  distinctionId: number,
  name: string,
  text: string,
  beatId: number = BEAT.beat_id
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
  cost_per_rank: 2,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
  // The life page shows a beat the offers whose opener is that beat.
  opener_key: `beat:${beatId}`,
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
  offer(101, 1, 'Hard scrabble', 'Nothing came easy, and you learned to make do.'),
  offer(102, 2, 'Spoiled', 'Whatever you wanted, someone fetched it.'),
  offer(103, 3, 'Bookish', 'You were raised among books and little else.'),
];
const SECOND_OFFERS = [
  offer(201, 21, 'Apprenticed', 'A master took you on and worked you hard.', SECOND_BEAT.beat_id),
  offer(202, 22, 'Tutored', 'Someone was paid to teach you letters.', SECOND_BEAT.beat_id),
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

test.describe('character creation: a clicked card shows at once (#5134)', () => {
  test('the card is picked before the save answers, and the list is not asked for again', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 1500 });
    const draft = await mockCg(page, CRADLE);
    // The suggested life is already loaded for this beginning: nothing to load on mount.
    (draft.draft_data as Record<string, unknown>) = { life_loaded_for: BEGINNING.id };

    let held: Entry[] = [];
    const listRequests: number[] = [];
    let saveAnswered = false;
    const SAVE_MS = 4000;
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
        listRequests.push(Date.now());
        await route.fulfill({ json: held });
      } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/sync/`) {
        const body = route.request().postDataJSON() as {
          distinctions: { id: number; rank: number; offer_id: number }[];
        };
        held = body.distinctions.map((row) => {
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
        saveAnswered = true;
        await route.fulfill({ json: { distinctions: held, stat_adjustments: [] } });
      } else {
        await route.fallback();
      }
    });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await page.goto('/characters/create');
    const card = page.getByRole('button', { name: /^Hard scrabble/ });
    const sibling = page.getByRole('button', { name: /^Spoiled/ });
    await expect(card).toBeVisible({ timeout: 15000 });
    await expect(card).toHaveAttribute('aria-pressed', 'false');
    const listRequestsBefore = listRequests.length;

    const clicked = Date.now();
    await card.click();
    // The save takes four seconds; the card is picked well inside one.
    await expect(card).toHaveAttribute('aria-pressed', 'true', { timeout: 1000 });
    expect(Date.now() - clicked).toBeLessThan(1000);
    // The other cards wait for the save: a second save would be built on the old list.
    await expect(sibling).toBeDisabled();
    await page.waitForTimeout(500);
    await page.screenshot({ path: shot('1-picked-before-the-save-answers.png'), fullPage: true });
    expect(saveAnswered).toBe(false);

    // When the save answers the card stays picked, the others open again, and the page
    // has not gone back for the list: the save's answer is the list.
    await expect(sibling).toBeEnabled({ timeout: SAVE_MS + 3000 });
    expect(saveAnswered).toBe(true);
    await expect(card).toHaveAttribute('aria-pressed', 'true');
    await page.waitForTimeout(1500);
    expect(listRequests.length).toBe(listRequestsBefore);
    await page.screenshot({ path: shot('2-after-the-save-answers.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  /**
   * Two beats on one page, each its own card grid with its own save. On the build
   * before #5134 the second grid did not know the first grid's save was in flight: a
   * click there was built from the list that save was replacing, and the first pick was
   * lost. `EVIDENCE_OLD_BUILD=1` runs this walk against that build and expects the loss;
   * without it the walk expects the second grid held until the first save answers, and
   * both picks kept.
   */
  test('a pick in a second beat does not cost the first beat its pick', async ({ page }) => {
    const oldBuild = process.env.EVIDENCE_OLD_BUILD === '1';
    await page.setViewportSize({ width: 1280, height: 1500 });
    const draft = await mockCg(page, CRADLE);
    (draft.draft_data as Record<string, unknown>) = { life_loaded_for: BEGINNING.id };

    const all = [...OFFERS, ...SECOND_OFFERS];
    let held: Entry[] = [];
    const saves: number[][] = [];
    let answered = 0;
    await page.route('**/api/**', async (route: Route) => {
      const url = new URL(route.request().url());
      const p = url.pathname;
      const method = route.request().method();
      if (p === `/api/character-creation/drafts/${DRAFT_ID}/beats/`) {
        await route.fulfill({ json: [BEAT, SECOND_BEAT] });
      } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/offers/`) {
        const chapter = url.searchParams.get('chapter');
        await route.fulfill({ json: { offers: chapter === 'backgrounds' ? all : [], terms: [] } });
      } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/` && method === 'GET') {
        await route.fulfill({ json: held });
      } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/sync/`) {
        const body = route.request().postDataJSON() as {
          distinctions: { id: number; rank: number; offer_id: number }[];
        };
        const first = saves.length === 0;
        saves.push(body.distinctions.map((row) => row.offer_id));
        // A save replaces the draft's whole list, as the server does.
        const mine: Entry[] = body.distinctions.map((row) => {
          const picked = all.find((o) => o.offer_id === row.offer_id)!;
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
        held = mine;
        // The first save is the slow one; the second answers quickly.
        await new Promise((resolve) => setTimeout(resolve, first ? 4000 : 300));
        answered += 1;
        await route.fulfill({ json: { distinctions: mine, stat_adjustments: [] } });
      } else {
        await route.fallback();
      }
    });

    await page.goto('/characters/create');
    const first = page.getByRole('button', { name: /^Hard scrabble/ });
    await expect(first).toBeVisible({ timeout: 15000 });
    await first.click();

    // The second beat's cards, while the first beat's save is still in flight. Since
    // #5160 every section is open on arrival; the build before #5134 had to open it.
    if (oldBuild) await page.getByRole('button', { name: /What you were taught/ }).click();
    const second = page.getByRole('button', { name: /^Apprenticed/ });
    await expect(second).toBeVisible();
    expect(answered).toBe(0);

    if (oldBuild) {
      // Before #5134: the card is open, the click is taken, and its save carries the
      // second pick alone, so the server ends holding one card.
      await expect(second).toBeEnabled();
      await second.click();
      await expect.poll(() => answered, { timeout: 8000 }).toBe(2);
      expect(saves).toEqual([[101], [201]]);
      expect(held.map((entry) => entry.offer_ids[0])).toEqual([201]);
      await page.waitForTimeout(1500);
      await page.screenshot({ path: shot('old-build-first-pick-lost.png'), fullPage: true });
      return;
    }

    // Since #5134: the second grid is held until the first save answers.
    await expect(second).toBeDisabled();
    await page.screenshot({ path: shot('3-second-beat-held-during-the-save.png'), fullPage: true });
    await expect(second).toBeEnabled({ timeout: 8000 });
    await second.click();
    await expect.poll(() => answered, { timeout: 8000 }).toBe(2);
    // The second save carries both picks, and the server holds both.
    expect(saves).toEqual([[101], [101, 201]]);
    expect(held.map((entry) => entry.offer_ids[0])).toEqual([101, 201]);
    await expect(second).toHaveAttribute('aria-pressed', 'true');
    await page.waitForTimeout(800);
    await page.screenshot({ path: shot('4-both-picks-kept.png'), fullPage: true });
  });
});
