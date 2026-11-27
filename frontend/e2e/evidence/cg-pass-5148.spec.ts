import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Locator, type Page, type Route } from '@playwright/test';
import { BEGINNING, CRADLE, DRAFT_ID, mockCg } from './fixtures/cgLineage';

/**
 * Review evidence for #5148, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * Three things in character creation: the right-hand panel on the life page (Lineage)
 * is the same "CG selections" panel as on every other stage, with the life's choices
 * listed under it; a trait on a card's mechanics line shows its definition on hover;
 * "View in Codex" opens the codex in a new tab. `EVIDENCE_OLD_BUILD=1` only takes the
 * pictures of the life page's panel and of a hovered trait, for the build before #5148.
 */
const here = path.dirname(fileURLToPath(import.meta.url));
const oldBuild = process.env.EVIDENCE_OLD_BUILD === '1';
const shot = (name: string) =>
  path.join(here, '..', '..', 'test-results', 'cg-pass-5148', (oldBuild ? 'old-' : '') + name);

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

type Effect = { target: string; label: string; value: number; immune: boolean };
const offer = (offerId: number, name: string, text: string, cost: number, effects: Effect[]) => ({
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
  opener_key: `beat:${BEAT.beat_id}`,
  first_look: true,
  held: false,
  effect_line: '',
  taken_per_feature: false,
  cg_max_rank: 0,
  group: '',
  asks_figure_name: false,
  effects,
});
const OFFERS = [
  offer(101, 'Bookish', 'You were raised among books and little else.', 15, [
    { target: 'poise', label: 'poise', value: 10, immune: false },
    { target: 'menace', label: 'menace', value: -5, immune: false },
  ]),
  offer(102, 'Hard scrabble', 'Nothing came easy, and you learned to make do.', -10, [
    { target: 'menace', label: 'menace', value: 5, immune: false },
  ]),
  // A trait nobody has written a definition for.
  offer(103, 'Well travelled', 'You had seen three kingdoms before you were ten.', 5, [
    { target: 'wayfinding', label: 'wayfinding', value: 5, immune: false },
  ]),
];
const POISE = 'How well you hold yourself under the eyes of a room. Added to social defence.';
const TERMS = [
  { name: 'poise', label: 'poise', definition: POISE },
  { name: 'menace', label: 'menace', definition: 'How much others fear to cross you.' },
  { name: 'wayfinding', label: 'wayfinding', definition: '' },
];
const CODEX_ENTRY = {
  id: 31,
  name: 'Misbegotten',
  summary: 'Those born of the Tree of Souls.',
  quote: '',
  companion: null,
  lore_content: 'Raised in the Cradle, with no family but each other.',
  mechanics_content: null,
  lore_links: [],
  mechanics_links: [],
  is_public: true,
  is_featured: false,
  featured_order: null,
  subject: 1,
  subject_name: 'Beginnings',
  subject_path: [{ type: 'subject', id: 1, name: 'Beginnings' }],
  display_order: 0,
  knowledge_status: 'known',
  known_by: [],
  learn_threshold: 10,
  research_progress: null,
  art_url: null,
  perspective_of: null,
  also_filed_under: [],
};
const held = () =>
  [OFFERS[0], OFFERS[1]].map((o) => ({
    distinction_id: o.distinction_id,
    distinction_name: o.name,
    distinction_slug: o.name.toLowerCase().replace(/ /g, '-'),
    category_slug: 'background',
    rank: 1,
    cost: o.cost_per_rank,
    notes: '',
    offer_ids: [o.offer_id],
    sources: [BEAT.name],
    arrivals: ['choice'],
  }));

/** Character creation with Bookish (15) and Hard scrabble (the world pays 10) held. */
async function creation(page: Page, stage: number, firstCard: boolean) {
  const draft = await mockCg(page, CRADLE);
  const server = { held: held(), saves: 0 };
  const spent = server.held.reduce((sum, entry) => sum + entry.cost, 0);
  (draft.draft_data as Record<string, unknown>) = {
    life_loaded_for: BEGINNING.id,
    distinctions: server.held,
  };
  draft.cg_points_spent = spent;
  draft.cg_points_remaining = 100 - spent;
  (draft as unknown as { current_stage: number }).current_stage = stage;
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();
    if (p === `/api/character-creation/drafts/${DRAFT_ID}/beats/`) {
      await route.fulfill({ json: [BEAT] });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/offers/`) {
      const chapter = url.searchParams.get('chapter') ?? '';
      await route.fulfill({
        json: { offers: chapter === 'backgrounds' ? OFFERS : [], terms: TERMS },
      });
    } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/` && method === 'GET') {
      await route.fulfill({ json: server.held });
    } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/sync/`) {
      server.saves += 1;
      await route.fulfill({ status: 400, json: { detail: 'No save is expected in this walk.' } });
    } else if (p === '/api/character-creation/beginnings/') {
      await route.fulfill({ json: [{ ...BEGINNING, codex_entry_ids: [CODEX_ENTRY.id] }] });
    } else if (p === `/api/codex/entries/${CODEX_ENTRY.id}/`) {
      await route.fulfill({ json: CODEX_ENTRY });
    } else {
      await route.fallback();
    }
  });
  await page.goto('/characters/create');
  if (firstCard) {
    await expect(page.getByRole('button', { name: /^Bookish/ })).toBeVisible({ timeout: 15000 });
  }
  return { server, draft: draft as unknown as { current_stage: number } };
}

const panelOf = (page: Page) => page.locator('.interview .chapter > aside');

/** The "CG selections" part of the right-hand panel: what it reads and how it is set. */
async function selections(page: Page) {
  const panel = panelOf(page);
  const style = (target: Locator) =>
    target.evaluate((el) => {
      const s = getComputedStyle(el);
      return {
        fontFamily: s.fontFamily,
        fontSize: s.fontSize,
        fontWeight: s.fontWeight,
        letterSpacing: s.letterSpacing,
        textTransform: s.textTransform,
        color: s.color,
      };
    });
  const box = (await panel.boundingBox())!;
  return {
    heading: await panel.locator('.record-rail .rail-label').textContent(),
    labels: await panel.locator('.record-rail dt').allTextContents(),
    values: await panel.locator('.record-rail dd').allTextContents(),
    stageLine: await panel.locator('.rail-ledger').textContent(),
    box: { x: Math.round(box.x), width: Math.round(box.width) },
    panelBorder: await panel.evaluate((el) => getComputedStyle(el).borderLeft),
    headingStyle: await style(panel.locator('.record-rail .rail-label')),
    labelStyle: await style(panel.locator('.record-rail dt').first()),
    valueStyle: await style(panel.locator('.record-rail dd').first()),
    stageLineStyle: await style(panel.locator('.rail-ledger')),
  };
}

test.describe('character creation, three fixes from a look at production (#5148)', () => {
  test('the life page has the same right-hand panel as Heritage, with the choices under it', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const { draft } = await creation(page, 3, true);
    await page.screenshot({ path: shot('1-life-page-panel.png') });
    if (oldBuild) return;

    const life = await selections(page);
    expect(life.heading).toBe('CG selections');
    expect(life.labels).toEqual(['Origin', 'Beginnings', 'Species', 'Gender', 'CG points']);
    expect(life.values).toEqual(['Arx City', 'Misbegotten', 'Human', 'Female', '5 of 100 spent']);
    expect(life.stageLine).toBe('Stage 3 of 10');

    // The choices come after it in the same panel, by life stage, with their prices.
    const panel = panelOf(page);
    const choices = panel.getByRole('region', { name: 'Life So Far' });
    await expect(choices).toBeVisible();
    await expect(choices.locator('.st')).toHaveText(['Childhood']);
    await expect(choices.locator('.row')).toHaveText(['Bookish−15', 'Hard scrabble+10']);
    const recordBottom = await panel
      .locator('.record-rail')
      .evaluate((el) => el.getBoundingClientRect().bottom);
    expect((await choices.boundingBox())!.y).toBeGreaterThanOrEqual(recordBottom);
    // No box of its own, and none of the old lines.
    await expect(panel).not.toContainText(/Starting|Remaining|Gained/);
    await expect(page.locator('.interview .ledger .tot')).toHaveCount(0);
    expect(await choices.evaluate((el) => getComputedStyle(el).borderTopWidth)).toBe('0px');
    await expect(page.locator('.interview .chapter > aside')).toHaveCount(1);
    await expect(page.locator('.interview .ledger')).toHaveCount(1);

    // The panel stays beside the cards when the page is scrolled to its foot.
    await page.locator('.interview .page-turn').scrollIntoViewIfNeeded();
    await expect(panel.locator('.record-rail .rail-label')).toBeInViewport();
    await page.screenshot({ path: shot('2-life-page-scrolled.png') });

    // Heritage, the stage before: the same panel in the same place, set the same way.
    draft.current_stage = 2;
    await page.reload();
    await expect(page.locator('.interview .chapter-no')).toHaveText('Stage 2 of 10');
    const heritage = await selections(page);
    await page.screenshot({ path: shot('3-heritage-panel.png') });
    expect(heritage.labels).toEqual(life.labels);
    expect(heritage.values).toEqual(life.values);
    expect(heritage.stageLine).toBe('Stage 2 of 10');
    expect(heritage.box).toEqual(life.box);
    expect(heritage.panelBorder).toBe(life.panelBorder);
    expect(heritage.headingStyle).toEqual(life.headingStyle);
    expect(heritage.labelStyle).toEqual(life.labelStyle);
    expect(heritage.valueStyle).toEqual(life.valueStyle);
    expect(heritage.stageLineStyle).toEqual(life.stageLineStyle);
    expect(errors).toEqual([]);
  });

  test('under 74rem the panel stands under the stage, on the life page as on Heritage', async ({
    page,
  }) => {
    test.skip(oldBuild, 'the old build is pictured at desktop width only');
    await page.setViewportSize({ width: 1100, height: 900 });
    const { draft } = await creation(page, 3, true);
    const panel = panelOf(page);
    const main = page.locator('.interview .chapter > .chapter-main');
    const mainBox = (await main.boundingBox())!;
    const panelBox = (await panel.boundingBox())!;
    expect(panelBox.y).toBeGreaterThanOrEqual(mainBox.y + mainBox.height);
    expect(Math.round(panelBox.x)).toBe(Math.round(mainBox.x));
    await expect(panel.getByRole('region', { name: 'Life So Far' }).locator('.row')).toHaveCount(2);
    await panel.scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('4-life-page-panel-at-1100.png') });

    draft.current_stage = 2;
    await page.reload();
    await expect(page.locator('.interview .chapter-no')).toHaveText('Stage 2 of 10');
    const heritageMain = (await main.boundingBox())!;
    const heritagePanel = (await panel.boundingBox())!;
    expect(heritagePanel.y).toBeGreaterThanOrEqual(heritageMain.y + heritageMain.height);
    expect(Math.round(heritagePanel.x)).toBe(Math.round(heritageMain.x));
  });

  test('a trait on a card shows its definition on hover, on focus and on a click', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    const { server } = await creation(page, 3, true);
    // A card is a box picked by the button on its name (#5206); an effect with a
    // definition is a button of its own on the card, its number with its term.
    const bookish = page.getByRole('button', { name: /^Bookish/ });
    const bookishCard = page.locator('.stance', { has: bookish });
    const poise = bookishCard.locator('.effect', { hasText: 'poise' });
    const box = page.locator('.popover');

    await expect(box).toHaveCount(0);
    // Bring the card into the window first and let the scroll finish: scrolling closes
    // the box, and `hover()` would otherwise scroll and point in one step.
    await bookishCard.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await poise.hover();
    await page.screenshot({ path: shot('5-hover-on-poise.png') });
    if (oldBuild) {
      // Before #5148 only a click opened anything, and this is what it opened.
      await poise.click();
      await page.screenshot({ path: shot('5b-click-on-poise.png') });
      return;
    }
    await expect(box).toBeVisible();
    await expect(box).toHaveText(`poise${POISE}`);
    // The box is a small card just under the word, inside the window, with its own
    // ground: its style rules reach it (before #5148 none did, and it was a blank sheet
    // the height of the page).
    const word = (await poise.boundingBox())!;
    const card = (await box.boundingBox())!;
    expect(card.y).toBeGreaterThanOrEqual(word.y + word.height);
    expect(card.y).toBeLessThan(word.y + word.height + 12);
    expect(Math.abs(card.x - word.x)).toBeLessThan(2);
    expect(card.width).toBeLessThanOrEqual(352);
    expect(card.height).toBeLessThan(160);
    const set = await box.evaluate((el) => {
      const s = getComputedStyle(el);
      return { position: s.position, border: s.borderTopWidth, background: s.backgroundColor };
    });
    expect(set.position).toBe('fixed');
    expect(set.border).toBe('1px');
    expect(set.background).not.toBe('rgba(0, 0, 0, 0)');
    await expect(box.getByText(POISE)).toBeInViewport();

    // Moving to another trait swaps the box; moving off the card removes it.
    await bookishCard.locator('.effect', { hasText: 'menace' }).hover();
    await expect(box).toHaveText('menaceHow much others fear to cross you.');
    await page.mouse.move(5, 5);
    await expect(box).toHaveCount(0);

    // After a scroll has closed the box, the next movement over the word shows it again.
    await poise.hover();
    await expect(box).toBeVisible();
    await page.mouse.wheel(0, 40);
    await expect(box).toHaveCount(0);
    await page.waitForTimeout(300);
    const at = (await poise.boundingBox())!;
    await page.mouse.move(at.x + at.width / 2 + 1, at.y + at.height / 2);
    await expect(box).toHaveText(`poise${POISE}`);
    await page.mouse.move(5, 5);
    await expect(box).toHaveCount(0);

    // A click pins it: it stays when the pointer leaves, and Escape closes it.
    await poise.click();
    await page.mouse.move(5, 5);
    await expect(box).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(box).toHaveCount(0);

    // The keyboard: the focus arriving shows it, the focus moving on shows the next.
    // (The click left the focus on the word, so step off it and come back.)
    await page.keyboard.press('Shift+Tab');
    await expect(box).toHaveCount(0);
    await page.keyboard.press('Tab');
    await expect(poise).toBeFocused();
    await expect(box).toHaveText(`poise${POISE}`);
    await page.keyboard.press('Tab');
    await expect(box).toHaveText('menaceHow much others fear to cross you.');
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Shift+Tab');
    await expect(box).toHaveCount(0);

    // None of that picked or dropped a card.
    expect(server.saves).toBe(0);
    await expect(bookish).toHaveAttribute('aria-pressed', 'true');

    // A trait with no definition written is plain text: no underline, nothing to open.
    const travelled = page.locator('.stance', {
      has: page.getByRole('button', { name: /^Well travelled/ }),
    });
    await expect(travelled.locator('.fx')).toHaveText('+5 wayfinding');
    await expect(travelled.locator('.term')).toHaveCount(0);
    expect(
      await bookishCard
        .locator('.term')
        .first()
        .evaluate((el) => getComputedStyle(el).textDecorationLine)
    ).toBe('underline');
  });

  test('View in Codex opens the codex in a new tab and leaves character creation where it was', async ({
    page,
    context,
  }) => {
    test.skip(oldBuild, 'the old build is pictured on the life page only');
    await page.setViewportSize({ width: 1366, height: 900 });
    await creation(page, 2, false);
    const codexLine = page.getByRole('button', { name: 'Codex: Misbegotten' });
    if (!(await codexLine.isVisible().catch(() => false))) {
      await page
        .getByRole('button', { name: /Misbegotten/ })
        .first()
        .click();
    }
    await codexLine.click();
    const overlay = page.getByRole('dialog');
    const link = overlay.getByRole('link', { name: 'View in Codex' });
    await expect(link).toBeVisible();
    // The overlay fades in; picture it once it has.
    await page.waitForTimeout(500);
    await page.screenshot({ path: shot('6-codex-overlay.png') });

    const opened = context.waitForEvent('page');
    await link.click();
    const tab = await opened;
    await tab.waitForLoadState('domcontentloaded');
    expect(new URL(tab.url()).pathname).toBe('/codex');
    expect(new URL(tab.url()).searchParams.get('entry')).toBe(String(CODEX_ENTRY.id));
    // The first tab has not moved: still character creation, the overlay still open.
    expect(new URL(page.url()).pathname).toBe('/characters/create');
    await expect(overlay).toBeVisible();
    await expect(page.locator('.interview .chapter-no')).toHaveText('Stage 2 of 10');
    expect(context.pages()).toHaveLength(2);
  });
});
