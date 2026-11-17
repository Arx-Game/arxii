import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';
import { BEGINNING, CRADLE, DRAFT_ID, mockCg } from './fixtures/cgLineage';

/**
 * Review evidence for #5160, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * The life page (Lineage) opens with every life stage and every section expanded, each
 * fold closes and opens by itself, and the box at the end of a stage is "Background
 * Notes" with a placeholder saying where the text goes. `EVIDENCE_OLD_BUILD=1` only
 * takes the pictures, for the build before #5160.
 */
const here = path.dirname(fileURLToPath(import.meta.url));
const oldBuild = process.env.EVIDENCE_OLD_BUILD === '1';
const shot = (name: string) =>
  path.join(here, '..', '..', 'test-results', 'cg-life-open-5160', (oldBuild ? 'old-' : '') + name);

const PLACEHOLDER =
  'You can write an optional description of what this stage of the character’s life was like, and it will be added to their listed Background on the character sheet.';

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
  opens_feature: false,
  requires_feature_opened: false,
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

test.describe('the life page opens expanded, and a stage ends on Background Notes (#5160)', () => {
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
    const cards = page.locator('.interview .life .stances.grid button.stance:not(.amnesiac)');
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

  for (const at of [
    { width: 1920, height: 1080 },
    { width: 1366, height: 900 },
    { width: 480, height: 844 },
    { width: 390, height: 844 },
    { width: 320, height: 640 },
  ]) {
    test(`Background Notes at ${at.width}px: the label, the whole placeholder in italics, and the text saved`, async ({
      page,
    }) => {
      await page.setViewportSize(at);
      const { saves } = await lifePage(page);
      const old = page.locator('#stage-desc-childhood');
      await old.scrollIntoViewIfNeeded();
      await page.screenshot({ path: shot(`6-notes-box-at-${at.width}.png`) });
      if (oldBuild) return;

      // One box per stage, each labelled Background Notes; the old label is nowhere.
      await expect(page.getByLabel('Background Notes')).toHaveCount(3);
      await expect(page.getByText('Description (Optional)')).toHaveCount(0);
      const box = stage(page, 'Childhood').getByLabel('Background Notes');
      await expect(box).toHaveAttribute('placeholder', PLACEHOLDER);
      await expect(box).toHaveValue('');

      // How the placeholder is drawn, and whether all of it fits in the box: a
      // placeholder cannot be scrolled, so a line that does not fit is a line unread.
      const drawn = await box.evaluate((el) => {
        const area = el as HTMLTextAreaElement;
        const own = getComputedStyle(area);
        const placeholder = getComputedStyle(area, '::placeholder');
        const pad = (side: string) => parseFloat(own.getPropertyValue(`padding-${side}`));
        const mirror = document.createElement('div');
        mirror.textContent = area.placeholder;
        Object.assign(mirror.style, {
          position: 'absolute',
          visibility: 'hidden',
          boxSizing: 'content-box',
          width: `${area.clientWidth - pad('left') - pad('right')}px`,
          fontFamily: own.fontFamily,
          fontSize: own.fontSize,
          lineHeight: own.lineHeight,
          letterSpacing: own.letterSpacing,
          fontStyle: placeholder.fontStyle,
          whiteSpace: 'pre-wrap',
          overflowWrap: 'break-word',
        });
        document.body.appendChild(mirror);
        const needed = mirror.getBoundingClientRect().height;
        mirror.remove();
        // The paper the box stands on: the nearest ancestor that paints a background.
        let paper = 'rgba(0, 0, 0, 0)';
        for (let node: Element | null = area; node; node = node.parentElement) {
          const bg = getComputedStyle(node).backgroundColor;
          if (bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
            paper = bg;
            break;
          }
        }
        return {
          fontStyle: placeholder.fontStyle,
          ink: placeholder.color,
          opacity: placeholder.opacity,
          paper,
          needed,
          room: area.clientHeight - pad('top') - pad('bottom'),
        };
      });
      expect(drawn.fontStyle).toBe('italic');
      expect(drawn.opacity).toBe('1');
      expect(drawn.needed).toBeLessThanOrEqual(drawn.room);
      // The ink reads against the paper: 4.5 to 1, the figure for body text.
      const channels = (color: string) => (color.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
      const luminance = (color: string) => {
        const [r, g, b] = channels(color).map((c) => {
          const v = c / 255;
          return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      };
      const [light, dark] = [luminance(drawn.ink), luminance(drawn.paper)].sort((a, b) => b - a);
      expect((light + 0.05) / (dark + 0.05)).toBeGreaterThanOrEqual(4.5);

      // Typing replaces the placeholder, and leaving the box saves that stage's text.
      await box.fill('Soft hands, hard lessons.');
      await page.screenshot({ path: shot(`7-notes-written-at-${at.width}.png`) });
      await stage(page, 'Youth').getByLabel('Background Notes').focus();
      await expect.poll(() => saves.length).toBe(1);
      expect(saves[0]).toEqual({
        draft_data: { stage_descriptions: { childhood: 'Soft hands, hard lessons.' } },
      });
      await expect(box).toHaveValue('Soft hands, hard lessons.');
      // The other stages' boxes are still empty and still show the placeholder.
      await expect(stage(page, 'Youth').getByLabel('Background Notes')).toHaveValue('');
    });
  }
});
