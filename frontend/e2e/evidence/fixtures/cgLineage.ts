import type { Page, Route } from '@playwright/test';

/**
 * The Lineage stage of `/characters/create` with every `/api/**` call answered by
 * fixtures shaped like the serializers: a Misbegotten draft at stage 3 and its two
 * Upbringings. Shared by the evidence walks that open Lineage (#4024, #5106).
 */
export type Upbringing = typeof CRADLE | typeof TAKEN_IN;

/** A family as `FamilySerializer` sends it to the claim path. */
export interface Family {
  id: number;
  name: string;
  kind: { id: number; name: string; styles_as_house: boolean };
  influence: number;
  standing: number | null;
  description: string;
  born_particle: string;
  taken_in_particle: string;
  inherited: { facets: unknown[]; features: unknown[]; liege_name: string };
}

export const DRAFT_ID = 9;
export const AREA = {
  id: 1,
  name: 'Arx City',
  description: 'The great capital city.',
  crest_image: null,
  realm_theme: 'arx',
  realm_slug: 'arx',
  realm_name: 'Arx',
};
export const BEGINNING = {
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
export const QUESTION = {
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
export const CRADLE = {
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
export const TAKEN_IN = {
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
      kind_name: 'Commoner',
      name_pattern: '^[A-Z][a-z]{2,19}$',
      name_hint: 'One word, capitalized.',
      charter_questions: [],
      features: [],
      served_house_choices: [],
      founds_a_crew: false,
      crew_slots: [],
    },
  ],
};
export const COPY = {
  upbringing_heading: 'Your Upbringing',
  tarot_no_parents_intro:
    'Children with no known parents are named by the tarot: a card drawn for them gives the surname they carry.',
  adoptive_family_heading: 'Your adoptive family',
};
export const TAROT = [
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

export function buildDraft(upbringing: Upbringing) {
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

export interface MockCgOptions {
  /** The families the claim path lists; none unless given. */
  families?: Family[];
  /** The family the draft has already picked. */
  family?: Family | null;
}

export async function mockCg(page: Page, upbringing: Upbringing, options: MockCgOptions = {}) {
  const draft = buildDraft(upbringing) as ReturnType<typeof buildDraft> & {
    family: Family | null;
  };
  if (options.family) {
    draft.family = options.family;
    draft.family_path = 'claimed';
  }
  const families = options.families ?? [];
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
    } else if (p === '/api/roster/families/' || p === '/api/character-creation/families/') {
      await route.fulfill({ json: families });
    } else if (/^\/api\/roster\/families\/\d+\/slots\/$/.test(p)) {
      await route.fulfill({ json: { slots: [], pools: [] } });
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
