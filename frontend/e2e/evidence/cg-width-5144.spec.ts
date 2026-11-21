import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';
import { BEGINNING, CRADLE, DRAFT_ID, mockCg } from './fixtures/cgLineage';

/**
 * Review evidence for #5144, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * Character creation at four window widths. On the life page (Lineage) the spread
 * follows the window and the card grids take the room. On a reading stage (Heritage)
 * the rails stand at the same two edges and the leaf keeps its reading width between
 * them. `EVIDENCE_OLD_BUILD=1` only takes the pictures, for the build before #5144.
 *
 * Since #5148 the life page's right-hand panel is the one every stage shows ("CG
 * selections", with the life's choices under it), not a ledger box of its own, and
 * under 74rem it stands under the stage as on every other stage. The life page test
 * measures that panel. The block that compared narrow windows box for box against the
 * build before #5144 is gone with the layout it compared.
 */
const here = path.dirname(fileURLToPath(import.meta.url));
const oldBuild = process.env.EVIDENCE_OLD_BUILD === '1';
const shot = (name: string) =>
  path.join(here, '..', '..', 'test-results', 'cg-width-5144', (oldBuild ? 'old-' : '') + name);

const beat = (id: number, name: string, prompt: string, stage: string, offers: number[]) => ({
  beat_id: id,
  name,
  prompt,
  life_stage: stage,
  selection: 'any',
  taken: false,
  unknown: false,
  line: '',
  answer_offer_ids: offers,
  allowance: null,
  allowance_is_points: false,
});

const offer = (offerId: number, beatId: number, name: string, text: string, cost: number) => ({
  offer_id: offerId,
  distinction_id: offerId,
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

const OFFERS = [
  offer(101, 1, 'Bookish', 'You were raised among books and little else.', 15),
  offer(102, 1, 'Hard scrabble', 'Nothing came easy, and you learned to make do.', -10),
  offer(103, 1, 'Well travelled', 'You had seen three kingdoms before you were ten.', 5),
  offer(104, 1, 'Doted on', 'Whatever you asked for, someone found a way to give you.', 10),
  offer(105, 1, 'Raised by servants', 'Your parents were names; the staff were family.', 0),
  offer(106, 1, 'Temple ward', 'The priests fed you, taught you, and expected much.', 5),
  offer(107, 1, 'Underfoot at court', 'You learned early who smiles and who means it.', 20),
  offer(108, 1, 'Sickly', 'You spent more of your childhood in bed than out of it.', -15),
  offer(201, 2, 'First blood', 'You won a fight you had no business winning.', 10),
  offer(202, 2, 'Ran away', 'You left home once, and came back changed.', -5),
  offer(203, 2, 'Apprenticed', 'A master took you on and worked you hard.', 10),
  offer(204, 2, 'A scandal', 'Everyone knows what you did that summer.', -10),
  offer(205, 2, 'First love', 'It ended, as these things do.', 0),
];
const BEATS = [
  beat(
    1,
    'How you were raised',
    'What was the house you grew up in like?',
    'childhood',
    [101, 102, 103, 104, 105, 106, 107, 108]
  ),
  beat(
    2,
    'What marked you',
    'What happened that you still carry?',
    'youth',
    [201, 202, 203, 204, 205]
  ),
];

/** Bookish (15) and Hard scrabble (the world pays 10) are already held. */
const HELD = [OFFERS[0], OFFERS[1]].map((o) => ({
  distinction_id: o.distinction_id,
  distinction_name: o.name,
  distinction_slug: o.name.toLowerCase().replace(/ /g, '-'),
  category_slug: 'background',
  rank: 1,
  cost: o.cost_per_rank,
  notes: '',
  offer_ids: [o.offer_id],
  sources: [BEATS[0].name],
  arrivals: ['choice'],
}));

async function lifePage(page: Page) {
  const draft = await mockCg(page, CRADLE);
  (draft.draft_data as Record<string, unknown>) = {
    life_loaded_for: BEGINNING.id,
    distinctions: HELD,
  };
  draft.cg_points_spent = 5;
  draft.cg_points_remaining = 95;
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    if (p === `/api/character-creation/drafts/${DRAFT_ID}/beats/`) {
      await route.fulfill({ json: BEATS });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/offers/`) {
      const chapter = url.searchParams.get('chapter') ?? '';
      await route.fulfill({ json: { offers: chapter === 'backgrounds' ? OFFERS : [], terms: [] } });
    } else if (
      p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/` &&
      route.request().method() === 'GET'
    ) {
      await route.fulfill({ json: HELD });
    } else {
      await route.fallback();
    }
  });
  await page.goto('/characters/create');
  await expect(page.getByRole('button', { name: /^Bookish/ })).toBeVisible({ timeout: 15000 });
}

/** How many cards sit on the first row of the open stage's grid. */
async function cardsOnFirstRow(page: Page) {
  const tops = await page
    .locator('.interview .life .stances.grid')
    .first()
    .locator(':scope > *')
    .evaluateAll((cards) => cards.map((card) => Math.round(card.getBoundingClientRect().top)));
  return tops.filter((top) => top === tops[0]).length;
}

const box = async (page: Page, selector: string) => {
  const found = await page.locator(selector).first().boundingBox();
  if (!found) throw new Error(`${selector} is not on the page`);
  return found;
};

/** A reading stage with something to read: Heritage, three beginnings and a species. */
async function heritagePage(page: Page) {
  const draft = await mockCg(page, CRADLE);
  (draft as unknown as { current_stage: number }).current_stage = 2;
  const prose =
    'Raised in the city among the guilds and the great houses, where every street has a ' +
    'patron and every patron a price.';
  const entry = (id: number, name: string) => ({
    id,
    name,
    description: prose,
    art_image: null,
    allowed_species_ids: [1],
    grants_species_languages: true,
    cg_point_cost: 0,
    codex_entry_ids: [],
    heritage: null,
    stat_bonuses: { strength: 1 },
    codex_entry_id: null,
    eternal_youth: false,
  });
  await page.route('**/api/**', async (route: Route) => {
    const p = new URL(route.request().url()).pathname;
    if (p === '/api/character-creation/beginnings/') {
      await route.fulfill({
        json: [entry(1, 'Normal Upbringing'), entry(2, 'Sleeper'), entry(3, 'Misbegotten')],
      });
    } else if (p === '/api/character-creation/species/') {
      await route.fulfill({ json: [entry(1, 'Human')] });
    } else {
      await route.fallback();
    }
  });
  await page.goto('/characters/create');
  await expect(page.locator('.entry-name', { hasText: 'Normal Upbringing' })).toBeVisible({
    timeout: 15000,
  });
}

const REM = 16;
/** The spread's side padding is clamp(1.25rem, 4vw, 3rem); its ceiling is 150rem. */
const sidePadding = (width: number) => Math.min(Math.max(0.04 * width, 1.25 * REM), 3 * REM);
const sideMargin = (width: number) => Math.max(0, (width - 150 * REM) / 2) + sidePadding(width);

const WIDTHS = [
  { name: 'desktop-1920', width: 1920, height: 1080, cards: 4 },
  { name: 'wide-2560', width: 2560, height: 1300, cards: 6 },
  { name: 'laptop-1366', width: 1366, height: 900, cards: 2 },
  { name: 'narrow-1100', width: 1100, height: 900, cards: 2 },
  { name: 'phone-390', width: 390, height: 844, cards: 2 },
];

test.describe('character creation uses the width of the window (#5144)', () => {
  for (const at of WIDTHS) {
    test(`the life page at ${at.width}px`, async ({ page }) => {
      await page.setViewportSize({ width: at.width, height: at.height });
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await lifePage(page);
      await page.screenshot({ path: shot(`${at.name}-top.png`) });
      // From 74rem of window the panel is the chapter's right-hand rail; under that it
      // stands under the stage (#5148).
      const railed = at.width >= 74 * REM;
      const panel = '.interview .chapter > aside';

      if (!oldBuild) {
        await expect(page.locator(panel)).toHaveCount(1);
        await expect(page.locator(`${panel} .ledger`)).toHaveCount(1);
        await expect(page.locator('.interview .ledger')).toHaveCount(1);
        const rail = await box(page, panel);
        const heading = await box(page, '.interview .chapter h1');
        const life = await box(page, '.interview .life');
        const leaf = await box(page, '.interview .chapter > .chapter-main');
        if (railed) {
          // At the right edge of the window, beside the stage from its heading down.
          const contents = await box(page, '.interview .toc-fold');
          expect(contents.x).toBeCloseTo(sideMargin(at.width), 0);
          expect(at.width - (rail.x + rail.width)).toBeCloseTo(sideMargin(at.width), 0);
          expect(rail.y).toBeLessThan(heading.y + heading.height + 2);
          expect(life.x + life.width).toBeLessThan(rail.x);
        } else {
          // Under the stage, the full width of the leaf.
          expect(rail.y).toBeGreaterThan(leaf.y + leaf.height - 1);
          expect(rail.x).toBeCloseTo(leaf.x, 0);
          expect(rail.width).toBeCloseTo(leaf.width, 0);
        }
      }

      await page.getByRole('button', { name: /^Bookish/ }).scrollIntoViewIfNeeded();
      await page.waitForTimeout(300);
      await page.screenshot({ path: shot(`${at.name}-life.png`) });
      await page.screenshot({ path: shot(`${at.name}-full.png`), fullPage: true });
      if (oldBuild) return;

      expect(await cardsOnFirstRow(page)).toBe(at.cards);
      if (railed) {
        // The panel has followed the scroll: it is in the window beside the cards.
        await page.locator('.interview .stage-acc').last().scrollIntoViewIfNeeded();
        const rail = await box(page, panel);
        expect(rail.y).toBeGreaterThanOrEqual(0);
        expect(rail.y + rail.height).toBeLessThanOrEqual(at.height);
      }
      await expect(
        page.locator('.interview .record-rail .row', { hasText: 'CG points' }).locator('dd')
      ).toHaveText('5 of 100 spent');
      expect(errors).toEqual([]);
    });
  }

  for (const at of [
    { name: 'desktop-1920', width: 1920, height: 1080 },
    { name: 'narrow-1100', width: 1100, height: 900 },
  ]) {
    test(`a reading stage at ${at.width}px`, async ({ page }) => {
      await page.setViewportSize({ width: at.width, height: at.height });
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await heritagePage(page);
      await page.screenshot({ path: shot(`${at.name}-heritage.png`), fullPage: true });
      if (oldBuild) return;

      const leaf = await box(page, '.interview .chapter > .chapter-main');
      const rail = await box(page, '.interview .chapter > aside');
      // The leaf keeps its reading width at any window width.
      expect(leaf.width).toBeCloseTo(38 * REM, 0);
      if (at.width >= 74 * REM) {
        const contents = await box(page, '.interview .toc-fold');
        expect(contents.x).toBeCloseTo(sideMargin(at.width), 0);
        expect(at.width - (rail.x + rail.width)).toBeCloseTo(sideMargin(at.width), 0);
        // Midway between the two rails: the same room on its left as on its right.
        const chapter = await box(page, '.interview .chapter');
        const left = leaf.x - chapter.x;
        const right = rail.x - (leaf.x + leaf.width);
        const gap = Math.min(Math.max(0.035 * at.width, 2 * REM), 3.5 * REM);
        expect(right - gap).toBeCloseTo(left, 0);
      } else {
        // Below 74rem the record sits under the leaf, as before.
        expect(rail.y).toBeGreaterThan(leaf.y + leaf.height - 1);
      }
      expect(errors).toEqual([]);
    });
  }
});
