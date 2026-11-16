import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Locator, type Page, type Route } from '@playwright/test';
import { BEGINNING, CRADLE, DRAFT_ID, mockCg } from './fixtures/cgLineage';

/**
 * Review evidence for #5146, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * The foot of a character creation stage: Back is the same button as Next, and on the
 * life page (Lineage) "Restart: Clear All Choices" stands between them, asks first, and
 * clears on confirm. "Start blank" is gone from under the cards. `EVIDENCE_OLD_BUILD=1`
 * only takes the picture of the foot, for the build before #5146.
 */
const here = path.dirname(fileURLToPath(import.meta.url));
const oldBuild = process.env.EVIDENCE_OLD_BUILD === '1';
const shot = (name: string) =>
  path.join(here, '..', '..', 'test-results', 'cg-restart-5146', (oldBuild ? 'old-' : '') + name);

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

const offer = (offerId: number, name: string, text: string, cost: number) => ({
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
  opens_feature: false,
  requires_feature_opened: false,
  cg_max_rank: 0,
  group: '',
  asks_figure_name: false,
  effects: [],
});
const OFFERS = [
  offer(101, 'Bookish', 'You were raised among books and little else.', 15),
  offer(102, 'Hard scrabble', 'Nothing came easy, and you learned to make do.', -10),
  offer(103, 'Well travelled', 'You had seen three kingdoms before you were ten.', 5),
];
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

/** The life page with Bookish (15) and Hard scrabble (the world pays 10) held. */
async function lifePage(page: Page) {
  const draft = await mockCg(page, CRADLE);
  const server = { held: held(), clears: 0 };
  const settle = () => {
    const spent = server.held.reduce((sum, entry) => sum + entry.cost, 0);
    (draft.draft_data as Record<string, unknown>) = {
      life_loaded_for: BEGINNING.id,
      distinctions: server.held,
    };
    draft.cg_points_spent = spent;
    draft.cg_points_remaining = 100 - spent;
  };
  settle();
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();
    if (p === `/api/character-creation/drafts/${DRAFT_ID}/beats/`) {
      await route.fulfill({ json: [BEAT] });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/offers/`) {
      const chapter = url.searchParams.get('chapter') ?? '';
      await route.fulfill({ json: { offers: chapter === 'backgrounds' ? OFFERS : [], terms: [] } });
    } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/` && method === 'GET') {
      await route.fulfill({ json: server.held });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/clear-life/`) {
      // What the server's clear does: the life's picks go, the rest of the draft stays.
      server.clears += 1;
      server.held = [];
      settle();
      await route.fulfill({ json: draft });
    } else {
      await route.fallback();
    }
  });
  await page.goto('/characters/create');
  await expect(page.getByRole('button', { name: /^Bookish/ })).toBeVisible({ timeout: 15000 });
  return server;
}

/** What makes two buttons look the same: the properties the two old styles differed in. */
const look = (button: Locator) =>
  button.evaluate((el) => {
    const s = getComputedStyle(el);
    return {
      fontFamily: s.fontFamily,
      fontStyle: s.fontStyle,
      fontSize: s.fontSize,
      fontWeight: s.fontWeight,
      letterSpacing: s.letterSpacing,
      textTransform: s.textTransform,
      textDecorationLine: s.textDecorationLine,
      color: s.color,
      backgroundColor: s.backgroundColor,
      border: `${s.borderTopWidth} ${s.borderTopStyle} ${s.borderTopColor}`,
      padding: s.padding,
      height: Math.round(el.getBoundingClientRect().height),
    };
  });

test.describe('the foot of a character creation stage (#5146)', () => {
  test('the life page: Back, Restart: Clear All Choices, Next; Restart asks, then clears', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const server = await lifePage(page);
    const foot = page.locator('.interview .page-turn');
    await foot.scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('1-foot-of-the-life-page.png') });
    if (oldBuild) return;

    // Three doors, in this order, and nothing reading "Start blank" anywhere.
    await expect(foot.getByRole('button')).toHaveText([
      'Back: Heritage',
      'Restart: Clear All Choices',
      'Next: Path',
    ]);
    await expect(page.getByText(/start blank/i)).toHaveCount(0);
    await expect(page.locator('.interview .life-foot button')).toHaveCount(0);

    // The three look the same, and Back is upright.
    const back = foot.getByRole('button', { name: 'Back: Heritage' });
    const restart = foot.getByRole('button', { name: 'Restart: Clear All Choices' });
    const next = foot.getByRole('button', { name: 'Next: Path' });
    const nextLook = await look(next);
    expect(await look(back)).toEqual(nextLook);
    expect(await look(restart)).toEqual(nextLook);
    expect(nextLook.fontStyle).toBe('normal');
    expect(nextLook.textDecorationLine).toBe('none');
    // Left to right on one line.
    const boxes = await Promise.all([back, restart, next].map((door) => door.boundingBox()));
    expect(boxes[0]!.x + boxes[0]!.width).toBeLessThan(boxes[1]!.x);
    expect(boxes[1]!.x + boxes[1]!.width).toBeLessThan(boxes[2]!.x);
    expect(boxes[1]!.y).toBe(boxes[0]!.y);
    expect(boxes[2]!.y).toBe(boxes[0]!.y);

    const ledger = page.getByRole('complementary', { name: 'CG points' });
    const rows = () => ledger.locator('.row').allTextContents();
    expect(await rows()).toEqual(['Bookish−15', 'Hard scrabble+10']);

    // Restart asks first: a dialog, and nothing sent.
    await restart.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading')).toHaveText('Restart: Clear All Choices');
    await expect(dialog).toContainText(
      'This removes every choice under Life So Far. Your family and the other stages are kept.'
    );
    expect(server.clears).toBe(0);
    await page.screenshot({ path: shot('2-restart-asks-first.png') });

    // Cancel: the dialog goes, nothing is sent, the picks stand.
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog).toBeHidden();
    expect(server.clears).toBe(0);
    expect(await rows()).toEqual(['Bookish−15', 'Hard scrabble+10']);
    await expect(page.getByRole('button', { name: /^Bookish/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    );

    // Confirm: one clear, the life is empty, the points are back.
    await restart.click();
    await dialog.getByRole('button', { name: 'Clear all choices' }).click();
    await expect(dialog).toBeHidden();
    await expect(ledger.getByText('Nothing chosen yet.')).toBeVisible();
    expect(server.clears).toBe(1);
    expect(await ledger.locator('.tot').allTextContents()).toEqual(['Starting100', 'Remaining100']);
    await expect(page.getByRole('button', { name: /^Bookish/ })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    await expect(page.getByRole('button', { name: /^Hard scrabble/ })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    await page.getByRole('button', { name: /^Bookish/ }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('3-cleared.png') });
    expect(errors).toEqual([]);
  });

  test('the life page on a phone: the three doors stack, full width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await lifePage(page);
    const foot = page.locator('.interview .page-turn');
    await foot.scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('4-foot-on-a-phone.png') });
    if (oldBuild) return;
    const doors = foot.getByRole('button');
    await expect(doors).toHaveCount(3);
    const boxes = await doors.evaluateAll((els) =>
      els.map((el) => {
        const r = el.getBoundingClientRect();
        return { text: el.textContent, x: Math.round(r.x), width: Math.round(r.width), y: r.y };
      })
    );
    // Forward on top, then Restart, then Back: the order the foot already stacked in.
    const topDown = [...boxes].sort((a, b) => a.y - b.y).map((box) => box.text);
    expect(topDown).toEqual(['Next: Path', 'Restart: Clear All Choices', 'Back: Heritage']);
    expect(new Set(boxes.map((box) => box.x)).size).toBe(1);
    expect(new Set(boxes.map((box) => box.width)).size).toBe(1);
  });

  test('another stage: Back looks like Next, and there is no Restart', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    const draft = await mockCg(page, CRADLE);
    (draft as unknown as { current_stage: number }).current_stage = 2;
    await page.goto('/characters/create');
    const foot = page.locator('.interview .page-turn');
    await expect(foot.getByRole('button', { name: /^Next:/ })).toBeVisible({ timeout: 15000 });
    await foot.scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('5-foot-of-heritage.png') });
    if (oldBuild) return;
    await expect(foot.getByRole('button')).toHaveText(['Back: Origin', 'Next: Lineage']);
    const back = await look(foot.getByRole('button', { name: 'Back: Origin' }));
    expect(back).toEqual(await look(foot.getByRole('button', { name: 'Next: Lineage' })));
    expect(back.fontStyle).toBe('normal');
  });
});
