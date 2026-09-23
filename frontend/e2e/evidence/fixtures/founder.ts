import type { ClaimableTitle, HouseTemplateOption } from '@/character-creation/api';

import { CHARTER, FERVOR, REALM_ID } from './inferna';

/**
 * Founder-journey fixtures (#3983 evidence harness, plates F-I onward) — the
 * CG draft that reaches Lineage stage 3 with the "Define a house" panel
 * already mounted (mirrors `frontend/e2e/almanach-founder.spec.ts`'s own
 * `buildDraft()`, Task 7 — same shape, renamed to Fervor/Inferna so the
 * founder screenshots read as the same worked example as the staff ones),
 * plus the claimable title/template Fervor's own duchy carries
 * (`founder.html:f2`'s House Quiddity list and principle axes verbatim).
 */

export const DRAFT_ID = 900;

export const FERVOR_TEMPLATE_ID = 950;

export const TEMPLATE: HouseTemplateOption = {
  id: FERVOR_TEMPLATE_ID,
  name: 'Charter of Fervor',
  description: 'The standard charter for a landed duchy of Inferna.',
  kind: 2,
  name_pattern: '.*',
  mercy_min: -5,
  mercy_max: 5,
  method_min: -5,
  method_max: 5,
  status_min: -5,
  status_max: 5,
  change_min: -5,
  change_max: 5,
  allegiance_min: -5,
  allegiance_max: 5,
  power_min: -5,
  power_max: 5,
  aspect_definitions: [
    {
      id: 1,
      name: 'House Quiddity',
      prompt:
        'What drives your house? A Quiddity is the thing an Infernal house is known for, the answer everyone else already has ready when your name comes up.',
      min_picks: 1,
      max_picks: 1,
      options: [
        {
          id: 101,
          name: 'Glamour',
          description:
            "Grandeur is the house's due, and a slight is answered before the ball has ended.",
          codex_entry_id: null,
        },
        {
          id: 102,
          name: 'Vendetta',
          description:
            'Claw and fang kept ready for the foes of the house. The grudge is always paid.',
          codex_entry_id: null,
        },
        {
          id: 103,
          name: 'The Covetous',
          description:
            "No advantage that cannot be bettered, whether by theft or by the sabotage of one's rivals.",
          codex_entry_id: null,
        },
        {
          id: 104,
          name: 'The Passions',
          description:
            'Better to be loved by somebody who can move a mountain. The work of the house is introductions.',
          codex_entry_id: null,
        },
        {
          id: 105,
          name: 'The Veiled',
          description: 'Deception as a way of life, in a realm where lying is a competitive sport.',
          codex_entry_id: null,
        },
        {
          id: 106,
          name: 'The Dread',
          description:
            'Far rather feared than loved, and content to empty a harbor without fighting it.',
          codex_entry_id: null,
        },
        {
          id: 107,
          name: 'The Leviathan',
          description:
            'The rarest Quiddity and believed the oldest. A reputation for ferocity it does very little to correct.',
          codex_entry_id: null,
        },
      ],
    },
  ],
  features: [
    { id: 1, name: 'Letter of Marque', slug: 'letter-of-marque', description: 'PLACEHOLDER' },
  ],
  holdings: [
    { id: 1, name: 'farmland' },
    { id: 2, name: 'a port' },
    { id: 3, name: 'a quarry' },
  ],
  default_succession_law: {
    id: 12,
    name: CHARTER.succession_law.name,
    codex_entry_id: CHARTER.succession_law.codex_entry_id,
  },
  starting_kin_slots: 3,
};

export const CLAIMABLE_TITLES: ClaimableTitle[] = [
  {
    id: FERVOR,
    name: 'Fervor',
    tier: 'duchy',
    realm_name: 'Inferna',
    seat_domain_name: '',
    templates: [TEMPLATE],
  },
];

/**
 * The draft opens already at Lineage (stage 3) with an area/heritage/
 * Upbringing picked and no family yet — the same shape as
 * `character-creation/__tests__/fixtures.ts`'s `mockDraftWithUpbringing`,
 * hand-copied here (standalone spec file convention, matching
 * `almanach-founder.spec.ts`'s own `buildDraft()`). `claimable_kind_ids: []`
 * deliberately (not the real content shape) so `showHouseFounding`
 * (`FamilyPathSection.tsx`) is true without also having to mock a
 * non-empty claimable-family list. `max_claim_tier: ''` permits every tier,
 * including Fervor's own duchy rank.
 */
export function buildDraft() {
  return {
    id: DRAFT_ID,
    current_stage: 3,
    selected_area: {
      id: 1,
      name: 'Perdition',
      description: 'The island capital of Inferna.',
      crest_image: null,
      realm_theme: 'inferna',
      realm_slug: 'inferna',
      realm_name: 'Inferna',
      realm_id: REALM_ID,
    },
    selected_beginnings: {
      id: 1,
      name: 'Ward of the House',
      description: 'Raised a ward of a noble house.',
      art_image: null,
      allowed_species_ids: [1, 2],
      grants_species_languages: true,
      cg_point_cost: 0,
      codex_entry_ids: [],
      heritage: null,
    },
    selected_species: { id: 1, name: 'Human', description: '' },
    selected_gender: { id: 2, key: 'woman', display_name: 'Woman' },
    public_worship: null,
    secret_worship: null,
    second_parent_species: null,
    age: 25,
    birthday_month: null,
    birthday_day: null,
    family: null,
    selected_origin_template: {
      id: 102,
      max_claim_tier: '',
      name: 'Ward of the House',
      frame_narrative: 'You grew up a ward of a noble house, claimed as one of its own.',
      is_active: true,
      sort_order: 2,
      cg_point_cost: 0,
      allows_claim_family: true,
      allows_name_family: false,
      allows_no_family: false,
      claimable_kind_ids: [] as number[],
      family_templates: [] as unknown[],
      slots: [] as unknown[],
    },
    family_path: 'claimed',
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
    stage_completion: {
      1: true,
      2: true,
      3: true,
      4: false,
      5: false,
      6: false,
      7: false,
      8: false,
      9: false,
      10: false,
      11: false,
    },
    has_existing_characters: false,
    stage_errors: {},
    stats_points_remaining: 5,
    stats_budget: 5,
    starting_technique_picks: 1,
    age_min: 18,
    age_max: 65,
    bundled_distinctions: [],
    derived_anchors: {},
    enemy_offers: [],
    enemy_price_tables: { group: {}, person: {} },
    enemy_degree_grants: {},
    enemy_reasons: [],
    introductions_offered: {},
  };
}
