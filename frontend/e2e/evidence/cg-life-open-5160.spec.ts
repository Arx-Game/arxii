import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';
import { BEGINNING, CRADLE, DRAFT_ID, mockCg } from './fixtures/cgLineage';

/**
 * Review evidence for #5160, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * The life page (Lineage) opens with every life stage and every section expanded, and
 * each fold closes and opens by itself. The Background Notes box this walk also covered
 * was removed by #5178 (one Background box on Final Touches; see
 * `cg-background-5178.spec.ts`). `EVIDENCE_OLD_BUILD=1` only takes the pictures, for the
 * build before #5160.
 */
const here = path.dirname(fileURLToPath(import.meta.url));
const oldBuild = process.env.EVIDENCE_OLD_BUILD === '1';
const shot = (name: string) =>
  path.join(here, '..', '..', 'test-results', 'cg-life-open-5160', (oldBuild ? 'old-' : '') + name);

const beat = (beatId: number, name: string, stage: string, offerIds: number[]) => ({
  beat_id: beatId,
  name,
  prompt: `${name}: what is true of those years.`,
  life_stage: stage,
  selection: 'any',
  taken: false,
  unknown: false,
  line: '',
  answer_offer_ids: offerIds,
  allowance: null,
  allowance_is_points: false,
});
const offer = (offerId: number, beatId: number, name: string, cost: number) => ({
  offer_id: offerId,
  distinction_id: offerId,
  name,
  distinction_name: name,
  distinction_description: `${name}: a line of what it meant, long enough to wrap on a card.`,
  player_line: name,
  chapter: 'backgrounds',
  arrives_as: 'choice',
  opener_label: '',
  cost_per_rank: cost,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
  opener_key: `beat:${beatId}`,
  first_look: true,
  held: false,
  effect_line: '',
  taken_per_feature: false,
  cg_max_rank: 0,
  group: '',
  asks_figure_name: false,
  effects: [],
});

// Five sections over three stages. The first is long, as the authored ones are: forty
// cards, taller than the window at any width the walk uses.
const NAMES: Record<number, string[]> = {
  1: Array.from({ length: 40 }, (_, i) => `Raised ${i + 1}`),
  2: ['Sickly', 'Hardy', 'Bookish'],
  3: ['Rival', 'Mentor', 'First love'],
  4: ['Spied for a house', 'Kept a shop', 'Went to sea'],
  5: ['Scarred', 'Indebted'],
};
const offersOf = (beatId: number) =>
  NAMES[beatId].map((name, i) => offer(beatId * 100 + i, beatId, name, i % 3 === 1 ? -5 : 5));
const OFFERS = [1, 2, 3, 4, 5].flatMap(offersOf);
const ids = (beatId: number) => offersOf(beatId).map((o) => o.offer_id);
const BEATS = [
  beat(1, 'How you were raised', 'childhood', ids(1)),
  beat(2, 'Your health', 'childhood', ids(2)),
  beat(3, 'Who shaped you', 'youth', ids(3)),
  beat(4, 'Known for', 'adulthood', ids(4)),
  beat(5, 'What marked it', 'adulthood', ids(5)),
];
const STAGES = ['Childhood', 'Youth', 'Before the Glimpse'];

/** The life page of a draft with nothing picked. Records every draft save. */
async function lifePage(page: Page) {
  const draft = await mockCg(page, CRADLE);
  const saves: Record<string, unknown>[] = [];
  (draft.draft_data as Record<string, unknown>) = { life_loaded_for: BEGINNING.id };
  (draft as unknown as { current_stage: number }).current_stage = 3;
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();
    if (p === `/api/character-creation/drafts/${DRAFT_ID}/beats/`) {
      await route.fulfill({ json: BEATS });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/offers/`) {
      const chapter = url.searchParams.get('chapter') ?? '';
      await route.fulfill({ json: { offers: chapter === 'backgrounds' ? OFFERS : [], terms: [] } });
    } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/` && method === 'GET') {
      await route.fulfill({ json: [] });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/` && method === 'PATCH') {
      const body = route.request().postDataJSON() as { draft_data?: Record<string, unknown> };
      saves.push(body);
      // The server merges `draft_data` by top-level key.
      Object.assign(draft.draft_data as Record<string, unknown>, body.draft_data ?? {});
      await route.fulfill({ json: draft });
    } else {
      await route.fallback();
    }
  });
  await page.goto('/characters/create');
  await expect(page.getByRole('region', { name: 'Childhood' })).toBeVisible({ timeout: 15000 });
  return { saves };
}

const stage = (page: Page, name: string) => page.getByRole('region', { name, exact: true });
const section = (page: Page, name: string) => page.getByRole('article', { name, exact: true });
/** A stage's heading button (its name starts with the fold mark, so it is found by class). */
const heading = (page: Page, name: string) => stage(page, name).locator('.stage-sum');
const line = (page: Page, beatId: number) => page.getByTestId(`sec-${beatId}`);

test.describe('the life page opens expanded (#5160)', () => {
  test('every stage and every section is open on arrival, with no click', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await lifePage(page);
    await page.screenshot({ path: shot('1-on-arrival.png') });
    await page.screenshot({ path: shot('1b-on-arrival-whole-page.png'), fullPage: true });
    if (oldBuild) return;

    for (const name of STAGES) {
      await expect(stage(page, name)).toHaveAttribute('data-open', 'true');
      await expect(heading(page, name)).toHaveAttribute('aria-expanded', 'true');
    }
    for (const b of BEATS) {
      await expect(section(page, b.name)).toHaveAttribute('data-open', 'true');
      await expect(line(page, b.beat_id)).toHaveAttribute('aria-expanded', 'true');
    }
    // Every card of every section is drawn: all fifty-one, each with a box on the page.
    const cards = page.locator('.interview .life .stances.grid .stance.pickable');
    await expect(cards).toHaveCount(OFFERS.length);
    const boxes = await cards.evaluateAll((els) =>
      els.map((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility === 'visible';
      })
    );
    expect(boxes.every(Boolean)).toBe(true);
    // The last section's cards are reached by scrolling alone.
    const last = page.getByRole('button', { name: /^Indebted/ });
    await last.scrollIntoViewIfNeeded();
    await expect(last).toBeInViewport();
    await page.screenshot({ path: shot('2-scrolled-to-the-last-section.png') });
    expect(errors).toEqual([]);
  });

  test('a fold closes and opens by itself; Next folds its section and shows the one below from its top', async ({
    page,
  }) => {
    test.skip(oldBuild, 'the build before #5160 keeps one fold open at a time');
    await page.setViewportSize({ width: 1366, height: 900 });
    await lifePage(page);

    const open = async () => ({
      stages: await page
        .locator('.interview .stage-acc')
        .evaluateAll((els) => els.map((el) => el.getAttribute('data-open'))),
      sections: await page
        .locator('.interview .sec')
        .evaluateAll((els) => els.map((el) => el.getAttribute('data-open'))),
    });
    expect(await open()).toEqual({
      stages: ['true', 'true', 'true'],
      sections: ['true', 'true', 'true', 'true', 'true'],
    });

    // A section's line folds that section and no other.
    await line(page, 4).click();
    expect(await open()).toEqual({
      stages: ['true', 'true', 'true'],
      sections: ['true', 'true', 'true', 'false', 'true'],
    });
    await expect(section(page, 'Known for').locator('.stances')).toHaveCount(0);
    // Folded with nothing picked, its line reads the prompt; an open section's line does
    // not, because its body prints the prompt.
    await expect(line(page, 4).locator('.ans')).toHaveText(
      'Known for: what is true of those years.'
    );
    await expect(line(page, 5).locator('.ans')).toHaveCount(0);
    await expect(section(page, 'What marked it').locator('.beat-prompt')).toHaveText(
      'What marked it: what is true of those years.'
    );
    await line(page, 4).scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('3-one-section-folded.png') });

    // A stage's heading folds that stage and no other; its sections are not drawn.
    await heading(page, 'Youth').click();
    expect((await open()).stages).toEqual(['true', 'false', 'true']);
    await expect(stage(page, 'Youth').getByRole('article')).toHaveCount(0);
    await expect(section(page, 'How you were raised')).toHaveAttribute('data-open', 'true');
    await page.screenshot({ path: shot('4-one-stage-folded.png') });

    // Both open again, as they were.
    await heading(page, 'Youth').click();
    await line(page, 4).click();
    expect(await open()).toEqual({
      stages: ['true', 'true', 'true'],
      sections: ['true', 'true', 'true', 'true', 'true'],
    });

    // Next at the foot of the long first section. Its forty cards are taller than the
    // window, so the top of the section is above the window when Next is pressed.
    const next = section(page, 'How you were raised').getByRole('button', { name: 'Next' });
    await next.scrollIntoViewIfNeeded();
    expect((await line(page, 1).boundingBox())!.y).toBeLessThan(0);
    await next.click();
    expect(await open()).toEqual({
      stages: ['true', 'true', 'true'],
      sections: ['false', 'true', 'true', 'true', 'true'],
    });
    // The folded section's line and the top of the section below are in the window.
    await expect(line(page, 1)).toBeInViewport({ ratio: 1 });
    await expect(line(page, 2)).toBeInViewport({ ratio: 1 });
    expect((await line(page, 2).boundingBox())!.y).toBeGreaterThan(
      (await line(page, 1).boundingBox())!.y
    );
    await page.screenshot({ path: shot('5-after-next.png') });

    // Next opens the section below when it had been folded by hand, and the next stage.
    await line(page, 3).click();
    await heading(page, 'Youth').click();
    expect((await open()).stages).toEqual(['true', 'false', 'true']);
    await section(page, 'Your health').getByRole('button', { name: 'Next' }).click();
    expect(await open()).toEqual({
      stages: ['true', 'true', 'true'],
      sections: ['false', 'false', 'true', 'true', 'true'],
    });
  });
});
