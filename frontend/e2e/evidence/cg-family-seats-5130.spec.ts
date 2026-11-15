import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';
import { TAKEN_IN, mockCg, type Family, type Seats } from './fixtures/cgLineage';

/**
 * Review evidence for #5130, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * Character creation at Lineage, joining an established family:
 *  - a family with no seat to take is not offered;
 *  - the family is entered through a seat: no card for joining without one, and
 *    no parents to name (a seat's parents are the ones staff wrote);
 *  - a seat card says what the seat is to the head of the house, prints no
 *    "(name set)", and marks only a name the player may change;
 *  - a picked seat is shown at once, before the server has answered.
 */
const here = path.dirname(fileURLToPath(import.meta.url));
const shot = (name: string) => path.join(here, '..', '..', 'test-results', 'cg-seats-5130', name);

const BORN = {
  ...TAKEN_IN,
  id: 192,
  name: 'Born to a house',
  parentage: 'known' as const,
  parentage_note: '',
};
const NOBLE = { id: 2, name: 'Noble', styles_as_house: true };
const KATTA: Family = {
  id: 4,
  name: 'Katta',
  kind: NOBLE,
  influence: 0,
  standing: null,
  description: 'The imperial house of Umbros, first in the shadow.',
  born_particle: 'mar',
  taken_in_particle: 'mal',
  inherited: { facets: [], features: [], liege_name: '' },
  has_open_seat: true,
};
/** A house with nobody to seat: it must not be offered. */
const VALEWEEP: Family = {
  ...KATTA,
  id: 5,
  name: 'Valeweep',
  description: 'A ducal house of the northern marches.',
  has_open_seat: false,
};
const seat = (id: number, name: string, over: Partial<Seats['slots'][number]> = {}) => ({
  id,
  name,
  name_locked: false,
  description: '',
  age_min: null,
  age_max: null,
  allowed_genders: [],
  family: KATTA.id,
  head_relation: null,
  ...over,
});
const KATTA_SEATS: Seats = {
  head_name: 'Alarysa',
  slots: [
    seat(11, 'Kathryn', { name_locked: true, head_relation: 'child', allowed_genders: ['Female'] }),
    seat(12, 'Tobren', { head_relation: 'niece/nephew', age_min: 16, age_max: 24 }),
    seat(13, 'Isolde', { head_relation: 'kin' }),
    seat(14, 'Marrow'),
  ],
  pools: [
    {
      id: 21,
      family: KATTA.id,
      description: 'A cousin of the line',
      count_remaining: 3,
      age_min: null,
      age_max: null,
      allowed_genders: [],
      parent_names: [],
    },
  ],
};

test.describe('character creation: an established family is joined through a seat (#5130)', () => {
  test('only a family with a seat is offered, and its seats say what they are', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 1500 });
    await mockCg(page, BORN as typeof TAKEN_IN, {
      families: [KATTA, VALEWEEP],
      seats: { [KATTA.id]: KATTA_SEATS },
    });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/characters/create');
    await page.getByRole('radio', { name: 'An established family' }).click();

    // Valeweep has no seat to take: it is not on the page at all.
    await expect(page.getByText('Katta', { exact: true })).toBeVisible();
    await expect(page.getByText('Valeweep')).toHaveCount(0);
    await page.waitForTimeout(300);
    await page.screenshot({ path: shot('1-only-families-with-a-seat.png'), fullPage: true });

    await page.getByText('Katta', { exact: true }).click();
    const kathryn = page.getByRole('button', { name: /^Kathryn/ });
    await expect(kathryn).toBeVisible();
    await expect(page.getByText('Your place in the family')).toBeVisible();

    // What each seat is to the head of the house.
    await expect(kathryn).toContainText('Child of Alarysa');
    await expect(page.getByRole('button', { name: /^Tobren/ })).toContainText(
      'Niece or nephew of Alarysa'
    );
    // Past sibling, cousin, niece or nephew the card says kin.
    await expect(page.getByRole('button', { name: /^Isolde/ })).toContainText('Kin of Alarysa');
    // A written name is the seat's; only one the player may change is marked.
    await expect(kathryn).not.toContainText('*');
    await expect(page.getByRole('button', { name: /^Tobren/ })).toContainText('Tobren*');
    await expect(page.getByText(/name set/i)).toHaveCount(0);
    await expect(page.getByText(/pre-authored/i)).toHaveCount(0);
    // No way in without a seat, and no parents to name.
    await expect(page.getByText(/no specific position/i)).toHaveCount(0);
    await expect(page.getByText(/your parents/i)).toHaveCount(0);
    await expect(
      page.getByRole('button', { name: /A cousin of the line \(3 left\)/ })
    ).toBeVisible();
    await page.waitForTimeout(300);
    await page.screenshot({ path: shot('2-seats-of-the-house.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('a picked seat shows before the server has answered', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1500 });
    await mockCg(page, BORN as typeof TAKEN_IN, {
      families: [KATTA],
      family: KATTA,
      seats: { [KATTA.id]: KATTA_SEATS },
      patchDelayMs: 4000,
    });
    await page.goto('/characters/create');
    const kathryn = page.getByRole('button', { name: /^Kathryn/ });
    const tobren = page.getByRole('button', { name: /^Tobren/ });
    await expect(kathryn).toHaveAttribute('aria-pressed', 'false');

    let answered = false;
    page.on('response', (response) => {
      if (response.request().method() === 'PATCH') answered = true;
    });
    const clicked = Date.now();
    await kathryn.click();
    // The server takes four seconds; the card is pressed well inside one.
    await expect(kathryn).toHaveAttribute('aria-pressed', 'true', { timeout: 1000 });
    const shown = Date.now() - clicked;
    expect(shown).toBeLessThan(1000);
    // The card's colour eases in over ~150 ms; let it settle, still inside the wait.
    await page.waitForTimeout(500);
    await page.screenshot({ path: shot('3-picked-before-the-answer.png'), fullPage: true });
    expect(answered).toBe(false);

    // Switching is as quick, and the first card lets go at once.
    await tobren.click();
    await expect(tobren).toHaveAttribute('aria-pressed', 'true', { timeout: 1000 });
    await expect(kathryn).toHaveAttribute('aria-pressed', 'false');
    await page.waitForTimeout(500);
    await page.screenshot({ path: shot('4-switched-before-the-answer.png'), fullPage: true });
    expect(answered).toBe(false);
  });
});
