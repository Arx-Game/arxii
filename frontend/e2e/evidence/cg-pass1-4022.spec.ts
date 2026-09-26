import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for the first CG walkthrough pass (#4022): the real
 * `/characters/create` page on the production bundle, every `/api/**` call
 * answered by fixtures shaped like the serializers. Captures Origin with a
 * realm chosen and nothing depending on it (no confirm on a change), the
 * chapter rail's plain hyphen notes, and Heritage with the Select mark on the
 * beginnings and species entries and the Gender section.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4022');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const DRAFT_ID = 7;
const AREAS = [
  {
    id: 1,
    name: 'Arx City',
    description: 'The great capital city, a hub of politics and intrigue.',
    crest_image: null,
    realm_theme: 'arx',
    realm_slug: 'arx',
    realm_name: 'Arx',
  },
  {
    id: 2,
    name: 'Perdition',
    description: 'The furnace capital of the Grand Principality.',
    crest_image: null,
    realm_theme: 'inferna',
    realm_slug: 'inferna',
    realm_name: 'The Grand Principality of Inferna',
  },
];
const BEGINNINGS = [
  {
    id: 1,
    name: 'Normal Upbringing',
    description: 'Raised in the city with a conventional background.',
    art_image: null,
    allowed_species_ids: [1, 2],
    grants_species_languages: true,
    cg_point_cost: 0,
    codex_entry_ids: [],
    heritage: null,
  },
  {
    id: 2,
    name: 'Sleeper',
    description: 'Awakened from magical slumber with no memory of origins.',
    art_image: null,
    allowed_species_ids: [1],
    grants_species_languages: false,
    cg_point_cost: 10,
    codex_entry_ids: [],
    heritage: null,
  },
];
const SPECIES = [
  {
    id: 1,
    name: 'Human',
    description: 'The most common species in the realm.',
    stat_bonuses: { strength: 1 },
    codex_entry_id: null,
    eternal_youth: false,
  },
  {
    id: 2,
    name: 'Khati',
    description: 'A feline species known for agility and perception.',
    stat_bonuses: { agility: 1 },
    codex_entry_id: null,
    eternal_youth: false,
  },
];
const GENDERS = [
  { id: 2, key: 'female', display_name: 'Female' },
  { id: 1, key: 'male', display_name: 'Male' },
  { id: 3, key: 'non_binary', display_name: 'Non-Binary' },
];

function buildDraft(stage: 1 | 2) {
  const completion: Record<number, boolean> = {};
  for (let s = 1; s <= 11; s += 1) completion[s] = false;
  completion[1] = true;
  const heritage = stage === 2;
  return {
    id: DRAFT_ID,
    current_stage: stage,
    selected_area: AREAS[0],
    selected_beginnings: heritage ? BEGINNINGS[0] : null,
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
    stage_errors: {
      2: ['Choose your beginnings, species and gender.'],
      3: ['Settle your family.'],
    },
    is_complete: false,
    submitted_at: null,
    created_at: '2026-09-26T00:00:00Z',
    updated_at: '2026-09-26T00:00:00Z',
  };
}

async function mockCg(page: Page, stage: 1 | 2) {
  const draft = buildDraft(stage);
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
    } else if (p === '/api/backgrounds/') {
      await route.fulfill({ json: [] });
    } else if (p === '/api/character-creation/can-create/') {
      await route.fulfill({ json: { can_create: true, reason: '' } });
    } else if (p === '/api/character-creation/explanations/') {
      await route.fulfill({ json: {} });
    } else if (p === '/api/character-creation/drafts/' && method === 'GET') {
      await route.fulfill({ json: [draft] });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/` && method === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      if ('selected_area_id' in body) {
        draft.selected_area = AREAS.find((a) => a.id === body.selected_area_id) ?? AREAS[0];
      }
      if ('selected_beginnings_id' in body) {
        draft.selected_beginnings =
          BEGINNINGS.find((b) => b.id === body.selected_beginnings_id) ?? null;
      }
      if ('selected_species_id' in body) {
        draft.selected_species = SPECIES.find((s) => s.id === body.selected_species_id) ?? null;
      }
      if ('selected_gender_id' in body) {
        draft.selected_gender = GENDERS.find((g) => g.id === body.selected_gender_id) ?? null;
      }
      await route.fulfill({ json: draft });
    } else if (p === '/api/character-creation/starting-areas/') {
      await route.fulfill({ json: AREAS });
    } else if (p === '/api/character-creation/beginnings/') {
      await route.fulfill({ json: BEGINNINGS });
    } else if (p === '/api/character-creation/species/') {
      await route.fulfill({ json: SPECIES });
    } else if (p === '/api/character-creation/genders/') {
      await route.fulfill({ json: GENDERS });
    } else if (p === '/api/worship/beings/') {
      await route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    } else if (p.endsWith('/perspectives/')) {
      await route.fulfill({ json: [] });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/cg-points/`) {
      await route.fulfill({ json: { spent: 0, remaining: 100, budget: 100, lines: [] } });
    } else if (method === 'GET') {
      await route.fulfill({ json: [] });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
  return draft;
}

test.describe('CG pass 1 (#4022): Origin and Heritage on the production bundle', () => {
  test('Origin: the mark on the chosen realm, a change with nothing dependent asks nothing', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const draft = await mockCg(page, 1);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/characters/create');

    const list = page.getByRole('list', { name: 'Starting realms' });
    await expect(list).toBeVisible();
    await expect(list.getByRole('button', { name: 'Selected Arx City' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    // The chapter rail's note reads after a hyphen, plain.
    await expect(page.locator('.toc-note').first()).toHaveText(
      '- Choose your beginnings, species and gender.'
    );
    await page.screenshot({ path: shot('origin-chosen-1280.png'), fullPage: true });

    // Nothing depends on the realm yet: pressing another realm's mark changes
    // it at once, with no "Change Starting Realm" dialog.
    await list.getByRole('button', { name: 'Select Perdition' }).click();
    await expect(page.getByRole('heading', { name: /change starting realm/i })).toHaveCount(0);
    await expect(list.getByRole('button', { name: 'Selected Perdition' })).toBeVisible();
    expect(draft.selected_area.name).toBe('Perdition');
    await page.screenshot({ path: shot('origin-changed-no-confirm-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('Heritage: Select marks on beginnings and species, the Gender section', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1400 });
    const draft = await mockCg(page, 2);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/characters/create');

    const beginnings = page.getByRole('list', { name: 'Beginnings' });
    await expect(beginnings).toBeVisible();
    await expect(
      beginnings.getByRole('button', { name: 'Selected Normal Upbringing' })
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(beginnings.getByRole('button', { name: 'Select Sleeper' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Gender' })).toBeVisible();
    await expect(page.getByText('Selected.')).toHaveCount(0);
    await page.screenshot({ path: shot('heritage-1280.png'), fullPage: true });

    // Selecting a species from its name row marks it and tints the row.
    await page.getByRole('button', { name: 'Select Khati' }).first().click();
    await expect(page.getByRole('button', { name: 'Selected Khati' })).toBeVisible();
    expect(draft.selected_species?.name).toBe('Khati');
    await page.screenshot({ path: shot('heritage-species-chosen-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('Heritage at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1400 });
    await mockCg(page, 2);
    await page.goto('/characters/create');
    await expect(page.getByRole('list', { name: 'Beginnings' })).toBeVisible();
    await page.screenshot({ path: shot('heritage-390.png'), fullPage: true });
  });
});
