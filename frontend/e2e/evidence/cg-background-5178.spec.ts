import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';
import { BEGINNING, CRADLE, DRAFT_ID, mockCg } from './fixtures/cgLineage';

/**
 * Review evidence for #5178, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * The life page (Lineage) asks for no free text about the life: no Background Notes at
 * the end of a stage and no Recent History under the last one. Final Touches has one
 * Background box, saved as `draft_data.background` when the stage is left, and the
 * Review stage quotes it. `EVIDENCE_OLD_BUILD=1` only takes the pictures, for the build
 * before #5178.
 */
const here = path.dirname(fileURLToPath(import.meta.url));
const oldBuild = process.env.EVIDENCE_OLD_BUILD === '1';
const shot = (name: string) =>
  path.join(
    here,
    '..',
    '..',
    'test-results',
    'cg-background-5178',
    (oldBuild ? 'old-' : '') + name
  );

const PLACEHOLDER =
  'You can write an optional description of the character’s background, and it will be listed as their Background on the character sheet.';
const WRITTEN =
  'Born above her mother’s chandlery on the river side of the city.\n\nApprenticed at fourteen to a river pilot who drank.';

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
const NAMES: Record<number, string[]> = {
  1: ['Sickly', 'Hardy', 'Bookish'],
  2: ['Rival', 'Mentor', 'First love'],
  3: ['Kept a shop', 'Went to sea'],
};
const offersOf = (beatId: number) =>
  NAMES[beatId].map((name, i) => offer(beatId * 100 + i, beatId, name, i % 3 === 1 ? -5 : 5));
const OFFERS = [1, 2, 3].flatMap(offersOf);
const ids = (beatId: number) => offersOf(beatId).map((o) => o.offer_id);
const BEATS = [
  beat(1, 'Your health', 'childhood', ids(1)),
  beat(2, 'Who shaped you', 'youth', ids(2)),
  beat(3, 'Known for', 'adulthood', ids(3)),
];
const MONTHS = Array.from({ length: 12 }, (_, i) => `Month ${i + 1}`);

interface Opened {
  saves: Record<string, unknown>[];
}

/** Opens creation on `stageNo` of a draft whose life holds `beats`. Records every save. */
async function openStage(
  page: Page,
  stageNo: number,
  options: { beats?: typeof BEATS; sleeper?: boolean; draftData?: Record<string, unknown> } = {}
): Promise<Opened> {
  const draft = (await mockCg(page, CRADLE)) as unknown as Record<string, unknown>;
  const saves: Record<string, unknown>[] = [];
  draft.draft_data = { life_loaded_for: BEGINNING.id, first_name: 'Maren', ...options.draftData };
  draft.current_stage = stageNo;
  // What Final Touches and Review read off the draft beyond the Lineage fixture.
  Object.assign(draft, {
    final_touches_cards: [],
    final_touches_prompts: ['alter_ego'],
    organization_choices: [],
    crime_kinds: [],
    ic_month_names: MONTHS,
  });
  if (options.sleeper) {
    draft.selected_beginnings = {
      ...BEGINNING,
      strikes_childhood: true,
      strikes_youth: true,
      strikes_adulthood: true,
      struck_stages_text:
        'As a Sleeper, your new life begins now without any memory of who you might have been.',
    };
  }
  const beats = options.sleeper ? [] : (options.beats ?? BEATS);
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();
    if (p === `/api/character-creation/drafts/${DRAFT_ID}/beats/`) {
      await route.fulfill({ json: beats });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/offers/`) {
      const chapter = url.searchParams.get('chapter') ?? '';
      const offers = chapter === 'backgrounds' && !options.sleeper ? OFFERS : [];
      await route.fulfill({ json: { offers, terms: [] } });
    } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/` && method === 'GET') {
      await route.fulfill({ json: [] });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/` && method === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      saves.push(body);
      // The server merges `draft_data` by top-level key and keeps the stage it is told.
      Object.assign(
        draft.draft_data as Record<string, unknown>,
        (body.draft_data as Record<string, unknown> | undefined) ?? {}
      );
      if (typeof body.current_stage === 'number') draft.current_stage = body.current_stage;
      await route.fulfill({ json: draft });
    } else {
      await route.fallback();
    }
  });
  await page.goto('/characters/create');
  return { saves };
}

/** How tall `text` stands in a box of the text area's own width and type. */
async function heightOf(page: Page, selector: string, text: string) {
  return page.evaluate(
    ([sel, value]) => {
      const box = document.querySelector<HTMLTextAreaElement>(sel)!;
      const style = getComputedStyle(box);
      const mirror = document.createElement('div');
      for (const prop of ['fontFamily', 'fontSize', 'lineHeight', 'letterSpacing'] as const) {
        mirror.style[prop] = style[prop];
      }
      mirror.style.fontStyle = 'italic';
      mirror.style.whiteSpace = 'pre-wrap';
      mirror.style.position = 'absolute';
      mirror.style.visibility = 'hidden';
      mirror.style.width = `${box.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)}px`;
      mirror.textContent = value;
      document.body.append(mirror);
      const needed = mirror.getBoundingClientRect().height;
      mirror.remove();
      const room =
        box.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
      return { needed, room };
    },
    [selector, text] as const
  );
}

test.describe('one Background box on Final Touches replaces the life page’s text boxes (#5178)', () => {
  test('the life page asks for no free text: no notes at the end of a stage, no Recent History', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await openStage(page, 3);
    await expect(page.getByRole('region', { name: 'Childhood' })).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.interview .stage-acc')).toHaveCount(3);
    await page.locator('.interview .stage-acc').last().scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('life-1920.png') });
    if (oldBuild) return;
    await expect(page.getByText('Background Notes')).toHaveCount(0);
    await expect(page.getByText(/Recent History/)).toHaveCount(0);
    await expect(page.locator('.interview .life textarea')).toHaveCount(0);
    // Every stage is still there with its cards. The life ends on the last one: the foot
    // line this once checked for is gone (#5201).
    await expect(page.locator('.interview .stage-acc[data-open="true"]')).toHaveCount(3);
    await expect(page.locator('.interview .life-foot')).toHaveCount(0);
  });

  test('a Sleeper’s life page shows the beginning’s line and nothing to fill in', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await openStage(page, 3, { sleeper: true });
    const line = page.locator('.interview .life .absent');
    await expect(line).toHaveText(
      'As a Sleeper, your new life begins now without any memory of who you might have been.',
      { timeout: 15000 }
    );
    await line.scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('sleeper-life-1920.png') });
    if (oldBuild) return;
    await expect(page.locator('.interview .life textarea')).toHaveCount(0);
    await expect(page.getByText(/Recent History/)).toHaveCount(0);
    await expect(page.locator('.interview .stage-acc')).toHaveCount(0);
  });

  for (const at of [
    { width: 1920, height: 1080 },
    { width: 1366, height: 768 },
    { width: 390, height: 844 },
  ]) {
    test(`Final Touches at ${at.width}px: one Background box, its whole placeholder in italics, saved on leaving and quoted on Review`, async ({
      page,
    }) => {
      await page.setViewportSize(at);
      const { saves } = await openStage(page, 10);
      await expect(page.getByRole('heading', { name: 'Goals' })).toBeVisible({ timeout: 15000 });
      if (oldBuild) {
        await page.getByRole('heading', { name: 'The Introductions' }).scrollIntoViewIfNeeded();
        await page.screenshot({ path: shot(`final-touches-${at.width}.png`) });
        return;
      }
      const heading = page.getByRole('heading', { name: 'Background', exact: true });
      const box = page.getByRole('textbox', { name: 'Background', exact: true });
      await expect(heading).toBeVisible();
      await expect(box).toHaveCount(1);
      await expect(box).toHaveValue('');
      await expect(box).toHaveAttribute('placeholder', PLACEHOLDER);
      await expect(box).toHaveAttribute('maxlength', '4000');

      // The placeholder is the only explanation, so it reads: italic, and all of it
      // inside the box (a placeholder cannot be scrolled).
      const italic = await box.evaluate((el) => getComputedStyle(el, '::placeholder').fontStyle);
      expect(italic).toBe('italic');
      const empty = await heightOf(page, '#background', PLACEHOLDER);
      expect(empty.needed).toBeLessThanOrEqual(empty.room);

      // The box sits after the goals and before The Introductions. (The enemy section
      // that used to stand above it shows only to a draft holding an enemy card, #5255.)
      const order = await page.evaluate(() => {
        const top = (el: Element | null) => el!.getBoundingClientRect().top + window.scrollY;
        const named = (text: string) =>
          Array.from(document.querySelectorAll('.interview h2.section-h')).find(
            (h) => h.textContent?.trim() === text
          ) ?? null;
        return {
          goals: top(named('Goals')),
          background: top(document.querySelector('#background')),
          introductions: top(named('The Introductions')),
        };
      });
      expect(order.goals).toBeLessThan(order.background);
      expect(order.background).toBeLessThan(order.introductions);

      await heading.scrollIntoViewIfNeeded();
      await page.screenshot({ path: shot(`final-touches-empty-${at.width}.png`) });

      // A second face still writes its own Background inside its door.
      const door = page.locator('section.introduction').filter({ hasText: 'A second face' });
      await door.getByRole('button', { name: 'Write it' }).click();
      await expect(door.getByLabel('The story the world knows')).toBeVisible();

      await box.fill(WRITTEN);
      await heading.scrollIntoViewIfNeeded();
      await page.screenshot({ path: shot(`final-touches-written-${at.width}.png`) });

      // Leaving the stage sends the text as draft_data.background, in the stage's one save.
      await page.getByRole('button', { name: 'Next: Review' }).click();
      await expect
        .poll(() => saves.find((s) => 'draft_data' in s)?.draft_data)
        .toMatchObject({ background: WRITTEN });
      const sent = saves.find((s) => 'draft_data' in s)!.draft_data as Record<string, unknown>;
      expect(sent).not.toHaveProperty('stage_descriptions');
      expect(sent).not.toHaveProperty('recent_history');

      // Review quotes it under Background, with its paragraph break kept.
      const quoted = page.locator('.interview .written').filter({ hasText: 'Background' });
      await expect(quoted.locator('blockquote span')).toHaveText(WRITTEN, {
        timeout: 15000,
        useInnerText: true,
      });
      await quoted.scrollIntoViewIfNeeded();
      await page.screenshot({ path: shot(`review-${at.width}.png`) });
    });
  }

  test('an Identity save carries no background, and the Background written on Final Touches stands', async ({
    page,
  }) => {
    test.skip(oldBuild, 'main’s Identity stage still carries the value; nothing to picture');
    await page.setViewportSize({ width: 1366, height: 768 });
    const { saves } = await openStage(page, 9, { draftData: { background: WRITTEN } });
    const concept = page.getByLabel(/character concept/i);
    await expect(concept).toBeVisible({ timeout: 15000 });
    await concept.fill('A river pilot');
    await page.getByRole('button', { name: 'Next: Final Touches' }).click();
    await expect.poll(() => saves.find((s) => 'draft_data' in s)?.draft_data).toBeTruthy();
    const sent = saves.find((s) => 'draft_data' in s)!.draft_data as Record<string, unknown>;
    expect(sent).toMatchObject({ concept: 'A river pilot' });
    expect(sent).not.toHaveProperty('background');
    // Final Touches still shows the Background the draft held before the Identity save.
    await expect(page.locator('#background')).toHaveValue(WRITTEN, { timeout: 15000 });
  });
});
