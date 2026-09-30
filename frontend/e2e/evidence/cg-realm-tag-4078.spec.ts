import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for the Origin stage's realm tag (#4078): the real
 * `/characters/create` page on the production bundle, every `/api/**` call
 * answered by fixtures shaped like the serializers. The starting areas are the
 * rows this branch's `/api/character-creation/starting-areas/` returned against
 * a copy of the live realms, descriptions replaced, plus one area whose realm
 * has no formal name.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4078');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const DRAFT_ID = 7;

function area(
  id: number,
  name: string,
  realm_id: number,
  realm_name: string,
  realm_formal_name: string
) {
  const slug = realm_name.toLowerCase();
  return {
    id,
    name,
    description: 'PLACEHOLDER description, not the authored text.',
    crest_image: null,
    realm_theme: slug,
    realm_slug: slug,
    realm_name,
    realm_formal_name,
    realm_id,
  };
}

const AREAS = [
  area(1, "Kys G'Sheer", 6, 'Ariwn', 'The Kingdoms of Ariwn'),
  area(3, 'Perdition', 5, 'Inferna', 'Grand Principality of Inferna'),
  area(4, 'Salvation', 4, 'Luxen', 'The Holy Revolutionary Republic of Luxen'),
  area(6, 'Tenebrum', 3, 'Umbros', 'The Umbral Empire'),
  area(2, 'The Bonespire', 7, 'Aythirmok', 'The Kingdom of Aythirmok'),
  area(5, 'The City of Arx', 1, 'Arx', 'The Necropolis'),
  // A realm staff gave no formal name: the tag is the realm's plain name.
  { ...area(9, 'Unnamed Reach', 9, 'Default', ''), realm_theme: 'default' },
];

const EXPECTED_TAGS: [string, string][] = [
  ["Kys G'Sheer", 'The Kingdoms of Ariwn'],
  ['Perdition', 'Grand Principality of Inferna'],
  ['Salvation', 'The Holy Revolutionary Republic of Luxen'],
  ['Tenebrum', 'The Umbral Empire'],
  ['The Bonespire', 'The Kingdom of Aythirmok'],
  ['The City of Arx', 'The Necropolis'],
  ['Unnamed Reach', 'Default'],
];

function buildDraft() {
  const completion: Record<number, boolean> = {};
  for (let s = 1; s <= 11; s += 1) completion[s] = false;
  return {
    id: DRAFT_ID,
    current_stage: 1,
    selected_area: null,
    selected_beginnings: null,
    selected_species: null,
    selected_gender: null,
    public_worship: null,
    secret_worship: null,
    second_parent_species: null,
    age: null,
    birthday_month: null,
    birthday_day: null,
    family: null,
    selected_origin_template: null,
    family_path: '',
    claimed_kin_slot: null,
    claimed_kin_pool: null,
    selected_vacancy: null,
    served_house: null,
    defer_parents: false,
    height_band: null,
    height_inches: null,
    build: null,
    selected_path: null,
    selected_tradition: null,
    cg_points_spent: 0,
    cg_points_remaining: 100,
    stat_bonuses: {},
    draft_data: {},
    stage_completion: completion,
    stage_errors: { 1: ['Choose a starting realm.'] },
    is_complete: false,
    submitted_at: null,
    created_at: '2026-09-29T00:00:00Z',
    updated_at: '2026-09-29T00:00:00Z',
  };
}

async function mockCg(page: Page) {
  const draft = buildDraft();
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();
    if (p === '/api/user/') {
      await route.fulfill({
        json: {
          id: 1,
          username: 'walk-e2e',
          display_name: 'Walk E2E',
          email: '',
          email_verified: true,
          last_login: null,
          can_create_characters: true,
          is_staff: false,
          is_gm: false,
          available_characters: [],
          pending_applications: [],
          selected_entry_id: null,
          selected_entry: null,
        },
      });
    } else if (p === '/api/roster/entries/mine/') {
      await route.fulfill({ json: [] });
    } else if (p === '/api/character-creation/can-create/') {
      await route.fulfill({ json: { can_create: true, reason: '' } });
    } else if (p === '/api/character-creation/explanations/') {
      await route.fulfill({ json: {} });
    } else if (p === '/api/character-creation/drafts/' && method === 'GET') {
      await route.fulfill({ json: [draft] });
    } else if (p === '/api/character-creation/starting-areas/') {
      await route.fulfill({ json: AREAS });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/cg-points/`) {
      await route.fulfill({ json: { spent: 0, remaining: 100, budget: 100, lines: [] } });
    } else if (method === 'GET') {
      await route.fulfill({ json: [] });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
}

async function expectTags(page: Page) {
  const list = page.getByRole('list', { name: 'Starting realms' });
  await expect(list).toBeVisible();
  for (const [name, tag] of EXPECTED_TAGS) {
    const item = list.getByRole('listitem').filter({ hasText: name });
    await expect(item.locator('.entry-tag > span').first()).toHaveText(tag);
  }
  await expect(page.getByText('The Northlands')).toHaveCount(0);
}

test.describe('Origin realm tag (#4078) on the production bundle', () => {
  test('each area is tagged with the formal name its realm carries', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockCg(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/characters/create');
    await expectTags(page);
    await page.screenshot({ path: shot('origin-tags-1280.png'), fullPage: true });

    // The reading under an entry still names the realm plainly in its link.
    await page.locator('.entry-name', { hasText: 'The Bonespire' }).click();
    await expect(page.getByRole('link', { name: /About Aythirmok/ })).toBeVisible();
    await page.screenshot({ path: shot('origin-bonespire-open-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await mockCg(page);
    await page.goto('/characters/create');
    await expectTags(page);
    await page.screenshot({ path: shot('origin-tags-390.png'), fullPage: true });
  });
});
