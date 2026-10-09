import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4202 (the CG half): the real `/characters/create` page on the
 * production bundle, at the Lineage stage, every `/api/**` call answered by fixtures
 * shaped like the serializers (the parentage harness of #4024, with the "Taken In"
 * Upbringing offering two Family Templates). Reading: the name path's "Family template"
 * row with both templates, and the picked template's description under it.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4202');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const DRAFT_ID = 9;
const AREA = {
  id: 1,
  name: 'Arx City',
  description: 'The great capital city.',
  crest_image: null,
  realm_theme: 'arx',
  realm_slug: 'arx',
  realm_name: 'Arx',
};
const BEGINNING = {
  id: 7,
  name: 'Misbegotten',
  description: 'Born of the Tree of Souls, raised in the Cradle.',
  art_image: null,
  allowed_species_ids: [1],
  grants_species_languages: true,
  cg_point_cost: 0,
  codex_entry_ids: [],
  heritage: null,
};
const QUESTION = {
  id: 501,
  name: 'The Cradle',
  prompt: 'Who did you grow up beside in the Cradle?',
  example: '',
  sort_order: 0,
  is_required: false,
  applies_to: 'any',
  allows_text: true,
  kind: 'text',
  connection_kind: '',
  life_stage: '',
  anchor_source: '',
  anchor_org_type_id: null,
  anchor_society_id: null,
  anchor_orgs: [],
  exclude_covert: false,
  same_anchor_as_id: null,
  follow_up_to_id: null,
  shown_for_choice_ids: [],
  choices: [],
  derived_anchors: [],
  offers: [],
};
const CRADLE = {
  id: 190,
  max_claim_tier: '',
  name: 'Raised in the Cradle',
  frame_narrative: 'The Vigil carried you to the Cradle, and there you grew up.',
  is_active: true,
  sort_order: 1,
  cg_point_cost: 0,
  allows_claim_family: false,
  allows_name_family: false,
  allows_no_family: true,
  parentage: 'unknown',
  parentage_note:
    'The Tree of Souls leaves a child no mother and no father. Whoever went to the Tree for you is not known to you.',
  claimable_kind_ids: [],
  family_templates: [],
  slots: [QUESTION],
};
const TAKEN_IN = {
  ...CRADLE,
  id: 191,
  name: 'Taken In',
  frame_narrative: 'A family came to the Cradle and took you home.',
  sort_order: 2,
  allows_claim_family: true,
  allows_name_family: true,
  allows_no_family: false,
  parentage: 'adoptive',
  parentage_note:
    'Those who raised you chose you. They are your family by adoption, and you carry their name.',
  claimable_kind_ids: [2],
  family_templates: [
    {
      id: 30,
      name: 'Commoner family',
      description: 'A household of no standing: a trade, a street, a name the neighbours know.',
      kind_name: 'Commoner',
      name_pattern: '^[A-Z][a-z]{2,19}$',
      name_hint: 'One word, capitalized.',
      aspect_definitions: [],
      features: [],
      served_house_choices: [],
      founds_a_crew: false,
      crew_slots: [],
    },
    {
      id: 31,
      name: 'Fallen house',
      description: 'A noble name with nothing left behind it but the name.',
      kind_name: 'Noble',
      name_pattern: '^[A-Z][a-z]{2,19}$',
      name_hint: 'One word, capitalized.',
      aspect_definitions: [],
      features: [],
      served_house_choices: [],
      founds_a_crew: false,
      crew_slots: [],
    },
  ],
};
const COPY = {
  upbringing_heading: 'Your Upbringing',
  tarot_no_parents_intro:
    'Children with no known parents are named by the tarot: a card drawn for them gives the surname they carry.',
  adoptive_family_heading: 'Your adoptive family',
};
const TAROT = [
  {
    id: 1,
    name: 'The Star',
    arcana_type: 'major',
    suit: null,
    rank: 17,
    latin_name: 'Stella',
    description: 'Hope renewed.',
    description_reversed: 'Hope withheld.',
    surname_upright: 'Stella',
    surname_reversed: 'Nox',
  },
];

function buildDraft(upbringing: typeof CRADLE | typeof TAKEN_IN) {
  const completion: Record<number, boolean> = {};
  for (let s = 1; s <= 11; s += 1) completion[s] = s < 3;
  return {
    id: DRAFT_ID,
    current_stage: 3,
    selected_area: AREA,
    selected_beginnings: BEGINNING,
    selected_species: { id: 1, name: 'Human', description: '' },
    selected_gender: { id: 2, key: 'female', display_name: 'Female' },
    public_worship: null,
    secret_worship: null,
    second_parent_species: null,
    age: 20,
    birthday_month: null,
    birthday_day: null,
    family: null,
    selected_origin_template: upbringing,
    family_path: 'name',
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
    draft_data: { family_template_id: 30 },
    stage_completion: completion,
    stage_errors: {},
    has_existing_characters: false,
    stats_points_remaining: 0,
    stats_budget: 0,
    starting_technique_picks: 0,
    age_min: 16,
    age_max: 60,
    bundled_distinctions: [],
    derived_anchors: {},
    enemy_offers: [],
    enemy_price_tables: { group: {}, person: {} },
    enemy_degree_grants: {},
    enemy_reasons: [],
    introductions_offered: { first_journal: false },
    is_complete: false,
    submitted_at: null,
    created_at: '2026-09-27T00:00:00Z',
    updated_at: '2026-09-27T00:00:00Z',
  };
}

async function mockCg(page: Page, upbringing: typeof CRADLE | typeof TAKEN_IN) {
  const draft = buildDraft(upbringing);
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();
    if (p === '/api/user/') {
      await route.fulfill({
        json: {
          id: 1,
          username: 'lineage-e2e',
          display_name: 'Lineage E2E',
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
    } else if (p === '/api/character-creation/can-create/') {
      await route.fulfill({ json: { can_create: true, reason: '' } });
    } else if (p === '/api/character-creation/explanations/') {
      await route.fulfill({ json: COPY });
    } else if (p === '/api/character-creation/drafts/' && method === 'GET') {
      await route.fulfill({ json: [draft] });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/` && method === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      if ('selected_origin_template_id' in body) {
        draft.selected_origin_template =
          [CRADLE, TAKEN_IN].find((u) => u.id === body.selected_origin_template_id) ?? upbringing;
        draft.family_path = '';
      }
      if ('family_path' in body) draft.family_path = String(body.family_path);
      const data = body.draft_data as Record<string, unknown> | undefined;
      if (data && 'family_template_id' in data) {
        draft.draft_data = {
          ...draft.draft_data,
          family_template_id: data.family_template_id as number | null,
        };
      }
      await route.fulfill({ json: draft });
    } else if (p === '/api/character-creation/origin-templates/') {
      await route.fulfill({ json: [CRADLE, TAKEN_IN] });
    } else if (p === '/api/character-creation/tarot-cards/') {
      await route.fulfill({ json: TAROT });
    } else if (p === '/api/character-creation/naming-ritual-config/') {
      await route.fulfill({ json: { flavor_text: '', codex_entry_id: null } });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/cg-points/`) {
      await route.fulfill({
        json: {
          starting_budget: 100,
          spent: 0,
          remaining: 100,
          xp_conversion_rate: 1,
          breakdown: [],
        },
      });
    } else if (p === '/api/character-creation/genders/') {
      await route.fulfill({
        json: [
          { id: 2, key: 'female', display_name: 'Female' },
          { id: 1, key: 'male', display_name: 'Male' },
        ],
      });
    } else if (p === '/api/almanach/houses/' || p === '/api/worship/beings/') {
      await route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/offers/`) {
      await route.fulfill({ json: { offers: [], closed: [] } });
    } else if (method === 'GET') {
      await route.fulfill({ json: [] });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
  return draft;
}

test.describe('The name-path template picker (#4202) on the production bundle', () => {
  test('two offered templates: the row, and the picked one described under it', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 1600 });
    await mockCg(page, TAKEN_IN);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/characters/create');

    await expect(page.getByText(TAKEN_IN.parentage_note)).toBeVisible();
    const row = page.getByRole('group', { name: 'Family template' });
    await expect(row).toBeVisible();
    await expect(row.getByRole('button', { name: 'Commoner family' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect(row.getByRole('button', { name: 'Fallen house' })).toBeVisible();
    await expect(
      page.getByText('A household of no standing: a trade, a street, a name the neighbours know.')
    ).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot('03-cg-name-path-picker-1280.png'), fullPage: true });

    await row.getByRole('button', { name: 'Fallen house' }).click();
    await expect(
      page.getByText('A noble name with nothing left behind it but the name.')
    ).toBeVisible();
    await page.screenshot({ path: shot('04-cg-name-path-picked-second-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });
});
