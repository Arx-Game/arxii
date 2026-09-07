/**
 * Character Creation Test Fixtures
 *
 * Mock data for testing character creation flows.
 */

import type { CodexEntryDetail } from '@/codex/types';
import type { TechniqueEffectSummary } from '@/magic/types';
import type {
  Beginnings,
  Build,
  CGGiftOption,
  CGTechniqueOption,
  CharacterDraft,
  DraftData,
  EffectType,
  Family,
  FamilyTemplate,
  GiftDetail,
  HeightBand,
  OriginTemplate,
  Path,
  Resonance,
  ResonanceAssociation,
  Restriction,
  SchoolingLineRow,
  Species,
  Stage,
  StartingArea,
  Technique,
  TechniqueStyle,
  Tradition,
  Vacancy,
} from '../types';

// =============================================================================
// Beginnings
// =============================================================================

export const mockBeginnings: Beginnings = {
  id: 1,
  name: 'Normal Upbringing',
  description: 'Raised in the city with a conventional background.',
  art_image: null,
  allowed_species_ids: [1, 2],
  grants_species_languages: true,
  cg_point_cost: 0,
  is_accessible: true,
  codex_entry_ids: [],
  heritage: null,
};

export const mockBeginningsUnknownFamily: Beginnings = {
  id: 2,
  name: 'Sleeper',
  description: 'Awakened from magical slumber with no memory of origins.',
  art_image: null,
  allowed_species_ids: [1, 2, 3],
  grants_species_languages: false,
  cg_point_cost: 0,
  is_accessible: true,
  codex_entry_ids: [],
  heritage: null,
};

// =============================================================================
// Starting Areas
// =============================================================================

export const mockStartingArea: StartingArea = {
  id: 1,
  name: 'Arx City',
  description: 'The great capital city, a hub of politics and intrigue.',
  crest_image: '/images/arx-crest.png',
  is_accessible: true,
  realm_theme: 'arx',
};

export const mockStartingAreaNoHeritages: StartingArea = {
  id: 2,
  name: 'Northern Reaches',
  description: 'A cold, frontier region.',
  crest_image: null,
  is_accessible: true,
  realm_theme: 'default',
};

export const mockStartingAreaInaccessible: StartingArea = {
  id: 3,
  name: 'Hidden Vale',
  description: 'A secret location accessible only to trusted players.',
  crest_image: null,
  is_accessible: false,
  realm_theme: 'default',
};

export const mockStartingAreas: StartingArea[] = [
  mockStartingArea,
  mockStartingAreaNoHeritages,
  mockStartingAreaInaccessible,
];

// =============================================================================
// Species
// =============================================================================

export const mockSpeciesHuman: Species = {
  id: 1,
  name: 'Human',
  description: 'The most common species in the realm.',
  stat_bonuses: { strength: 1 },
  codex_entry_id: null,
  eternal_youth: false,
};

export const mockSpeciesElf: Species = {
  id: 2,
  name: 'Elf',
  description: 'Long-lived and graceful beings.',
  stat_bonuses: { agility: 1, intellect: 1 },
  codex_entry_id: null,
  eternal_youth: true,
};

export const mockSpeciesDwarf: Species = {
  id: 3,
  name: 'Dwarf',
  description: 'Stout and hardy folk.',
  stat_bonuses: { stamina: 1, willpower: 1 },
  codex_entry_id: null,
  eternal_youth: false,
};

export const mockSpeciesList: Species[] = [mockSpeciesHuman, mockSpeciesElf, mockSpeciesDwarf];

// =============================================================================
// Families
// =============================================================================

export const mockNobleFamily: Family = {
  id: 1,
  name: 'Valardin',
  kind: { id: 2, name: 'Noble', styles_as_house: true },
  influence: 0,
  description: 'An honorable noble house known for martial prowess.',
  born_particle: 'du',
  taken_in_particle: 'dau',
  inherited: { aspects: [], features: [], liege_name: '' },
};

export const mockNobleFamily2: Family = {
  id: 2,
  name: 'Velenosa',
  kind: { id: 2, name: 'Noble', styles_as_house: true },
  influence: 0,
  description: 'A cunning noble house with southern roots.',
  born_particle: 'za',
  taken_in_particle: 'zas',
  inherited: { aspects: [], features: [], liege_name: '' },
};

export const mockCommonerFamily: Family = {
  id: 3,
  name: 'Smith',
  kind: { id: 1, name: 'Commoner', styles_as_house: false },
  influence: 0,
  description: 'A common family of craftspeople.',
  born_particle: '',
  taken_in_particle: '',
  inherited: { aspects: [], features: [], liege_name: '' },
};

export const mockFamilies: Family[] = [mockNobleFamily, mockNobleFamily2, mockCommonerFamily];

// =============================================================================
// Upbringings (OriginTemplate, #3617)
// =============================================================================

export const mockUpbringingNamed: OriginTemplate = {
  id: 101,
  name: 'Caretaker family',
  frame_narrative: 'You were raised by a family who took you in and gave you their name.',
  is_active: true,
  sort_order: 1,
  cg_point_cost: 6,
  trust_required: 0,
  allows_claim_family: false,
  allows_name_family: true,
  allows_no_family: false,
  claimable_kind_ids: [],
  family_templates: [],
  slots: [
    {
      id: 201,
      name: 'family_trade',
      prompt: 'What trade did your adoptive family practice?',
      example: 'Weaving, smithing, farming...',
      sort_order: 1,
      is_required: true,
      applies_to: 'any',
      allows_text: true,
      kind: 'text',
      connection_kind: '',
      life_stage: '',
      anchor_source: '',
      same_anchor_as: null,
      follow_up_to: null,
      shown_for_choice_ids: [],
      groups: [],
      choices: [],
    },
  ],
};

export const mockUpbringingClaim: OriginTemplate = {
  id: 102,
  name: 'Ward of the House',
  frame_narrative: 'You grew up a ward of a noble house, claimed as one of its own.',
  is_active: true,
  sort_order: 2,
  cg_point_cost: 0,
  trust_required: 0,
  allows_claim_family: true,
  allows_name_family: false,
  allows_no_family: false,
  claimable_kind_ids: [2],
  family_templates: [],
  slots: [
    {
      id: 202,
      name: 'upbringing_favor',
      prompt: 'What favor does the house show you?',
      example: '',
      sort_order: 1,
      is_required: false,
      applies_to: 'claimed',
      allows_text: false,
      kind: 'pick',
      connection_kind: '',
      life_stage: '',
      anchor_source: '',
      same_anchor_as: null,
      follow_up_to: null,
      shown_for_choice_ids: [],
      groups: [],
      choices: [
        {
          id: 301,
          name: 'A private tutor',
          description: 'A dedicated tutor sharpened your mind.',
          cg_point_cost: 2,
          cost_per_influence: 0,
          trust_required: 0,
          offers: [],
          sort_order: 1,
        },
        {
          id: 302,
          name: "A seat at the house's table",
          description: "Standing scales with the house's reach.",
          cg_point_cost: 0,
          cost_per_influence: 1,
          trust_required: 0,
          offers: [],
          sort_order: 2,
        },
      ],
    },
  ],
};

export const mockUpbringingUnknown: OriginTemplate = {
  id: 103,
  name: 'Unknown Origins',
  frame_narrative: 'Your true family origins are shrouded in mystery.',
  is_active: true,
  sort_order: 3,
  cg_point_cost: 0,
  trust_required: 0,
  allows_claim_family: false,
  allows_name_family: false,
  allows_no_family: true,
  claimable_kind_ids: [],
  family_templates: [],
  slots: [],
};

/** Allows both claim and name paths, with one shared prompt and one claim-only prompt. */
export const mockUpbringingMultiPath: OriginTemplate = {
  id: 104,
  name: 'Open Upbringing',
  frame_narrative: 'Your family origins are yours to define.',
  is_active: true,
  sort_order: 4,
  cg_point_cost: 0,
  trust_required: 0,
  allows_claim_family: true,
  allows_name_family: true,
  allows_no_family: false,
  claimable_kind_ids: [2],
  family_templates: [],
  slots: [
    {
      id: 203,
      name: 'childhood_home',
      prompt: 'Describe your childhood home.',
      example: '',
      sort_order: 1,
      is_required: false,
      applies_to: 'any',
      allows_text: true,
      kind: 'text',
      connection_kind: '',
      life_stage: '',
      anchor_source: '',
      same_anchor_as: null,
      follow_up_to: null,
      shown_for_choice_ids: [],
      groups: [],
      choices: [],
    },
    {
      id: 204,
      name: 'house_expectation',
      prompt: 'What does the house expect of you?',
      example: '',
      sort_order: 2,
      is_required: false,
      applies_to: 'claimed',
      allows_text: true,
      kind: 'text',
      connection_kind: '',
      life_stage: '',
      anchor_source: '',
      same_anchor_as: null,
      follow_up_to: null,
      shown_for_choice_ids: [],
      groups: [],
      choices: [],
    },
  ],
};

/**
 * A group/person/branch Upbringing (#3660): a LISTED group question with a
 * priced choice that grants a Distinction, a PERSON follow-up naming someone
 * inside that group, a second GROUP follow-up shown only for one branch of
 * the first question's answer, and a plain write-in.
 */
export const mockUpbringingConnections: OriginTemplate = {
  id: 105,
  name: 'Kept by a House',
  frame_narrative: 'A Humble house took you in and put you to work.',
  is_active: true,
  sort_order: 5,
  cg_point_cost: 0,
  trust_required: 0,
  allows_claim_family: false,
  allows_name_family: false,
  allows_no_family: true,
  claimable_kind_ids: [],
  family_templates: [],
  slots: [
    {
      id: 401,
      name: 'kept_by',
      prompt: 'Which Humble house kept you',
      example: '',
      sort_order: 1,
      is_required: true,
      applies_to: 'any',
      allows_text: false,
      kind: 'group',
      connection_kind: 'raised_by',
      life_stage: 'childhood',
      anchor_source: 'listed',
      same_anchor_as: null,
      follow_up_to: null,
      shown_for_choice_ids: [],
      groups: [
        {
          id: 9001,
          name: 'House Orisant',
          gloss: 'Shipping, tithe contracts.',
          influence: 4,
        },
      ],
      choices: [
        {
          id: 501,
          name: 'Livery at table',
          description: '',
          cg_point_cost: 0,
          cost_per_influence: 0,
          trust_required: 0,
          offers: [],
          sort_order: 1,
        },
        {
          id: 502,
          name: 'Courier',
          description: '',
          cg_point_cost: 10,
          cost_per_influence: 0,
          trust_required: 0,
          offers: [
            {
              offer_id: 6077,
              distinction_id: 77,
              name: 'Kept Close',
              player_line: '',
              arrives_as: 'bundled',
              cost_per_rank: 15,
              max_rank: 1,
            },
          ],
          sort_order: 2,
        },
      ],
    },
    {
      id: 402,
      name: 'caretaker',
      prompt: 'Who in the house looked after you',
      example: '',
      sort_order: 2,
      is_required: false,
      applies_to: 'any',
      allows_text: false,
      kind: 'person',
      connection_kind: 'raised_by',
      life_stage: 'childhood',
      anchor_source: '',
      same_anchor_as: 401,
      follow_up_to: 401,
      shown_for_choice_ids: [],
      groups: [],
      choices: [],
    },
    {
      id: 403,
      name: 'courier_contact',
      prompt: 'Did your courier runs bring you to the Rouault',
      example: '',
      sort_order: 3,
      is_required: false,
      applies_to: 'any',
      allows_text: false,
      kind: 'group',
      connection_kind: 'served',
      life_stage: 'youth',
      anchor_source: 'listed',
      same_anchor_as: null,
      follow_up_to: 401,
      shown_for_choice_ids: [502],
      groups: [{ id: 9002, name: 'the Rouault', gloss: '', influence: 2 }],
      choices: [],
    },
    {
      id: 404,
      name: 'other_ties',
      prompt: 'Any other ties worth mentioning',
      example: '',
      sort_order: 4,
      is_required: false,
      applies_to: 'any',
      allows_text: true,
      kind: 'text',
      connection_kind: '',
      life_stage: '',
      anchor_source: '',
      same_anchor_as: null,
      follow_up_to: null,
      shown_for_choice_ids: [],
      groups: [],
      choices: [],
    },
  ],
};

/**
 * An own-family GROUP question (#3660 ruling L): the server is the only side
 * that can resolve the claimed family's house org, so this template's answer
 * lives entirely in `CharacterDraft.derived_anchors`, keyed by this slot's id.
 */
export const mockUpbringingOwnFamilyGroup: OriginTemplate = {
  id: 106,
  name: 'Born to the House',
  frame_narrative: 'You grew up under your family roof.',
  is_active: true,
  sort_order: 6,
  cg_point_cost: 0,
  trust_required: 0,
  allows_claim_family: true,
  allows_name_family: false,
  allows_no_family: false,
  claimable_kind_ids: [],
  family_templates: [],
  slots: [
    {
      id: 405,
      name: 'own_house',
      prompt: 'What did your house expect of you',
      example: '',
      sort_order: 1,
      is_required: true,
      applies_to: 'any',
      allows_text: false,
      kind: 'group',
      connection_kind: 'raised_by',
      life_stage: 'childhood',
      anchor_source: 'own_family',
      same_anchor_as: null,
      follow_up_to: null,
      shown_for_choice_ids: [],
      groups: [],
      choices: [],
    },
  ],
};

// =============================================================================
// Family Templates (#3648) and the name-path Upbringing that offers one
// =============================================================================

export const mockFamilyTemplate: FamilyTemplate = {
  id: 401,
  name: 'Regency Trust',
  description: 'A staff-authored template for houses answering to the Regency.',
  kind: 2,
  name_pattern: '',
  org_type: 1,
  aspect_definitions: [
    {
      id: 601,
      name: 'Charge',
      prompt: 'What does this house tend to?',
      min_picks: 1,
      max_picks: 1,
      options: [
        {
          id: 611,
          name: 'Granaries',
          description: 'Feeds the realm through lean years.',
          codex_entry_id: null,
        },
        {
          id: 612,
          name: 'Aqueducts',
          description: 'Keeps the water running.',
          codex_entry_id: null,
        },
      ],
    },
  ],
  features: [
    {
      id: 621,
      name: 'Old Money',
      slug: 'old-money',
      description: 'Wealth banked for generations shows in every detail.',
    },
  ],
  served_house_choices: [{ id: 501, name: 'House Regency' }],
};

export const mockUpbringingNamedWithTemplate: OriginTemplate = {
  ...mockUpbringingNamed,
  family_templates: [mockFamilyTemplate],
};

// =============================================================================
// Vacancies (#3648): openings on a staff family, priced for the draft
// =============================================================================

export const mockVacancyKin: Vacancy = {
  id: 801,
  name: 'Third Daughter',
  description: 'A quiet place among the family, hers to fill.',
  basis: 'kin',
  importance: 1,
  presumed_importance: 5,
  cost: 6,
  rank_name: 'Kin',
  count_remaining: 1,
  organization: {
    id: 1,
    name: 'House Valardin',
    family: { id: 1, name: 'Valardin', influence: 3 },
  },
  kin_pool: {
    id: 901,
    family: 1,
    description: 'Distant cousins fostered into the household.',
    count_remaining: 1,
    age_min: 18,
    age_max: 40,
    allowed_genders: [],
    parent_names: [],
  },
  kin_node: null,
};

export const mockVacancyRetainer: Vacancy = {
  id: 802,
  name: 'Household Guard',
  description: 'Sworn to the house, not born to it.',
  basis: 'retainer',
  importance: 0,
  presumed_importance: 0,
  cost: 0,
  rank_name: 'Retainer',
  count_remaining: null,
  organization: {
    id: 1,
    name: 'House Valardin',
    family: { id: 1, name: 'Valardin', influence: 3 },
  },
  kin_pool: null,
  kin_node: null,
};

// =============================================================================
// Height Bands
// =============================================================================

export const mockHeightBandAverage: HeightBand = {
  id: 1,
  name: 'average',
  display_name: 'Average',
  min_inches: 64,
  max_inches: 72,
  is_cg_selectable: true,
};

export const mockHeightBandTall: HeightBand = {
  id: 2,
  name: 'tall',
  display_name: 'Tall',
  min_inches: 73,
  max_inches: 78,
  is_cg_selectable: true,
};

// Not normally offered to players; Giant's Blood opens it (#3675 Task 15).
export const mockHeightBandTowering: HeightBand = {
  id: 3,
  name: 'towering',
  display_name: 'Towering',
  min_inches: 79,
  max_inches: 96,
  is_cg_selectable: false,
};

// =============================================================================
// Builds
// =============================================================================

export const mockBuildAverage: Build = {
  id: 1,
  name: 'average',
  display_name: 'Average',
  is_cg_selectable: true,
};

export const mockBuildAthletic: Build = {
  id: 2,
  name: 'athletic',
  display_name: 'Athletic',
  is_cg_selectable: true,
};

// =============================================================================
// Draft Data
// =============================================================================

export const mockEmptyDraftData: DraftData = {};

export const mockCompleteDraftData: DraftData = {
  first_name: 'Testchar',
  description: 'A tall figure with piercing eyes.',
  never_do: 'Bold and adventurous.',
  background: 'Born to humble origins but destined for greatness.',
  concept: 'A warrior seeking redemption.',
  quote: 'The dawn comes for all.',
  path_skills_complete: true,
  magic_complete: true,
};

// =============================================================================
// Character Drafts
// =============================================================================

export const mockEmptyDraft: CharacterDraft = {
  id: 1,
  current_stage: 1 as Stage,
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
  draft_data: mockEmptyDraftData,
  stage_completion: {
    1: false,
    2: false,
    3: false,
    4: false,
    5: false,
    6: false,
    7: false,
    8: false,
    9: false,
    10: false,
    11: false,
  } as Record<Stage, boolean>,
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
  enemy_price_tables: {
    group: {
      household: { annoyed: 3, thwarted: 6, ruined: 12, destroy: 18 },
      house: { annoyed: 8, thwarted: 16, ruined: 32, destroy: 48 },
      society: { annoyed: 15, thwarted: 30, ruined: 60, destroy: 90 },
      realm: { annoyed: 25, thwarted: 50, ruined: 100, destroy: 150 },
    },
    person: {
      quiescent: { annoyed: 1, thwarted: 2, ruined: 4, destroy: 6 },
      prospect: { annoyed: 2, thwarted: 4, ruined: 8, destroy: 12 },
      potential: { annoyed: 4, thwarted: 8, ruined: 16, destroy: 24 },
      puissant: { annoyed: 8, thwarted: 16, ruined: 32, destroy: 48 },
      true: { annoyed: 15, thwarted: 30, ruined: 60, destroy: 90 },
      grand: { annoyed: 15, thwarted: 30, ruined: 60, destroy: 90 },
    },
  },
  enemy_degree_grants: { ruined: 'Marked', destroy: 'Hunted' },
  introductions_offered: { first_journal: true },
};

export const mockDraftWithArea: CharacterDraft = {
  ...mockEmptyDraft,
  id: 2,
  selected_area: mockStartingArea,
  selected_beginnings: mockBeginnings,
  stage_completion: {
    ...mockEmptyDraft.stage_completion,
    1: true,
  } as Record<Stage, boolean>,
};

export const mockDraftWithHeritage: CharacterDraft = {
  ...mockDraftWithArea,
  id: 3,
  current_stage: 2 as Stage,
  selected_beginnings: mockBeginningsUnknownFamily,
  selected_species: mockSpeciesHuman,
  selected_gender: { id: 2, key: 'female', display_name: 'Female' },
  age: 25,
  selected_origin_template: mockUpbringingUnknown,
  family_path: 'none',
  cg_points_spent: 0,
  cg_points_remaining: 100,
  stage_completion: {
    ...mockEmptyDraft.stage_completion,
    1: true,
    2: true,
  } as Record<Stage, boolean>,
};

export const mockDraftWithFamily: CharacterDraft = {
  ...mockDraftWithHeritage,
  id: 4,
  current_stage: 3 as Stage,
  selected_beginnings: mockBeginnings,
  selected_species: mockSpeciesElf,
  family: mockNobleFamily,
  selected_origin_template: mockUpbringingClaim,
  family_path: 'claimed',
  cg_points_spent: 0,
  cg_points_remaining: 100,
  stat_bonuses: { agility: 1, intellect: 1 },
  stage_completion: {
    ...mockEmptyDraft.stage_completion,
    1: true,
    2: true,
    3: true,
  } as Record<Stage, boolean>,
};

// =============================================================================
// Lineage-stage drafts (#3617): a draft mid-Lineage with area + beginnings
// picked but no Upbringing yet, and one with an Upbringing already selected.
// =============================================================================

export const mockDraftWithHeritageNoUpbringing: CharacterDraft = {
  ...mockDraftWithArea,
  id: 7,
  current_stage: 3 as Stage,
  selected_species: mockSpeciesHuman,
  selected_gender: { id: 2, key: 'female', display_name: 'Female' },
  age: 25,
  selected_origin_template: null,
  family_path: '',
  stage_completion: {
    ...mockEmptyDraft.stage_completion,
    1: true,
    2: true,
  } as Record<Stage, boolean>,
};

export const mockDraftWithUpbringing: CharacterDraft = {
  ...mockDraftWithHeritageNoUpbringing,
  id: 8,
  selected_origin_template: mockUpbringingClaim,
  family_path: 'claimed',
};

export const mockCompleteDraft: CharacterDraft = {
  ...mockDraftWithFamily,
  id: 5,
  current_stage: 11 as Stage, // Stage.REVIEW
  height_band: mockHeightBandAverage,
  height_inches: 68,
  build: mockBuildAverage,
  draft_data: mockCompleteDraftData,
  cg_points_spent: 100,
  cg_points_remaining: 0,
  has_existing_characters: true,
  stage_completion: {
    1: true,
    2: true,
    3: true,
    4: true,
    5: true,
    6: true,
    7: true,
    8: true,
    9: true,
    10: true,
    11: true,
  } as Record<Stage, boolean>,
};

export const mockIncompleteDraft: CharacterDraft = {
  ...mockCompleteDraft,
  id: 6,
  stage_completion: {
    1: true,
    2: true,
    3: true,
    4: false, // incomplete
    5: true,
    6: true,
    7: false, // incomplete (Attributes & Skills)
    8: true,
    9: true,
    10: false, // incomplete
    11: false,
  } as Record<Stage, boolean>,
};

// =============================================================================
// Factory Functions
// =============================================================================

/**
 * Create a custom draft with overrides
 */
export function createMockDraft(overrides: Partial<CharacterDraft> = {}): CharacterDraft {
  return {
    ...mockEmptyDraft,
    ...overrides,
  };
}

// =============================================================================
// Magic System Fixtures
// =============================================================================

export const mockTechniqueStyles: TechniqueStyle[] = [
  { id: 1, name: 'Manifestation', description: 'Visible magical effects' },
  { id: 2, name: 'Subtle', description: 'Hidden or internal magic' },
  { id: 3, name: 'Prayer', description: 'Magic channeled through devotion' },
];

export const mockEffectTypes: EffectType[] = [
  {
    id: 1,
    name: 'Attack',
    description: 'Offensive magical effects',
    base_power: 10,
    base_anima_cost: 2,
    has_power_scaling: true,
  },
  {
    id: 2,
    name: 'Defense',
    description: 'Protective magical effects',
    base_power: 10,
    base_anima_cost: 2,
    has_power_scaling: true,
  },
  {
    id: 3,
    name: 'Flight',
    description: 'Magical movement through air',
    base_power: null,
    base_anima_cost: 3,
    has_power_scaling: false,
  },
];

export const mockRestrictions: Restriction[] = [
  {
    id: 1,
    name: 'Touch Range',
    description: 'Requires physical contact',
    power_bonus: 10,
    allowed_effect_type_ids: [1, 2],
  },
  {
    id: 2,
    name: 'Self Only',
    description: 'Can only target yourself',
    power_bonus: 15,
    allowed_effect_type_ids: [2],
  },
];

export const mockResonanceAssociations: ResonanceAssociation[] = [
  { id: 1, name: 'Shadows', description: 'Darkness and concealment', category: 'Concepts' },
  { id: 2, name: 'Fire', description: 'Heat and transformation', category: 'Elements' },
  { id: 3, name: 'Spiders', description: 'Webs, patience, predation', category: 'Animals' },
];

export const mockResonances: Resonance[] = [
  {
    id: 1,
    name: 'Shadow',
    category: 2,
    category_name: 'resonance',
    description: 'Affinity with darkness',
    display_order: 1,
    is_active: true,
    opposite: null,
    resonance_affinity: 'abyssal',
    codex_entry_id: null,
  },
  {
    id: 2,
    name: 'Flame',
    category: 2,
    category_name: 'resonance',
    description: 'Affinity with fire',
    display_order: 2,
    is_active: true,
    opposite: null,
    resonance_affinity: 'primal',
    codex_entry_id: null,
  },
];

export const mockTechnique: Technique = {
  id: 1,
  name: 'Shadow Strike',
  gift: 1,
  effect_type: 1,
  restriction_ids: [1],
  level: 5,
  intensity: 1,
  control: 1,
  anima_cost: 2,
  description: 'A strike from the shadows',
  tier: 1,
};

export const mockGiftDetail: GiftDetail = {
  id: 1,
  name: 'Whispers of Shadow',
  affinity_breakdown: { Abyssal: 2 },
  description: 'Mastery over shadows and darkness',
  resonances: mockResonances,
  resonance_ids: [1, 2],
  techniques: [mockTechnique],
  technique_count: 1,
};

// =============================================================================
// GiftStage Funnel Fixtures (#2426 Task 10)
// =============================================================================

export const mockPath: Path = {
  id: 1,
  name: 'The Wanderer',
  description: 'A path of restless travel and self-reliance.',
  stage: 1,
  minimum_level: 1,
  icon_url: null,
  icon_name: 'compass',
  aspects: ['Wanderlust'],
  codex_entry_ids: [],
};

/**
 * The standard schooling set (#3675): three stances, rank 0 through 2,
 * authored once and shared by every `living_masters` tradition.
 */
export const mockSchoolingRows: SchoolingLineRow[] = [
  {
    schooling_line_id: 1,
    rank: 0,
    name: 'Newly taken in',
    player_line: 'Taken in after the Glimpse.',
    price: 0,
    techniques: 1,
    grants_distinction_id: null,
    offer_id: null,
  },
  {
    schooling_line_id: 2,
    rank: 1,
    name: 'Trained for years',
    player_line: 'Trained since youth.',
    price: 1,
    techniques: 2,
    grants_distinction_id: 77,
    offer_id: 201,
  },
  {
    schooling_line_id: 3,
    rank: 2,
    name: 'Raised within it',
    player_line: 'Born to it.',
    price: 2,
    techniques: 3,
    grants_distinction_id: 77,
    offer_id: 202,
  },
];

export const mockTradition: Tradition = {
  id: 1,
  name: 'The Whispering Path',
  description: 'A tradition of quiet, patient magic learned through observation.',
  is_active: true,
  sort_order: 1,
  codex_entry_ids: [7],
  state: 'living_masters',
  state_line: 'Living masters. They will teach you, and they will ask what you do with it.',
  own_wording: '',
  refund: 0,
  schooling: mockSchoolingRows,
};

/** A self-taught tradition (#3675): no schooling set, a refund on the entry. */
export const mockSelfTaughtTradition: Tradition = {
  id: 2,
  name: 'Unbound',
  description: 'No tradition; you taught yourself, badly and alone.',
  is_active: true,
  sort_order: 2,
  codex_entry_ids: [],
  state: 'self_taught',
  state_line: 'Self-taught · slower to learn',
  own_wording: '',
  refund: -75,
  schooling: [],
};

export const mockCGGiftOption: CGGiftOption = {
  id: 1,
  name: 'Whispers of Shadow',
  description: 'Mastery over shadows and darkness.',
  kind: 'major',
  codex_entry_id: 12,
};

export const mockCGGiftOptions: CGGiftOption[] = [
  mockCGGiftOption,
  {
    id: 2,
    name: 'Flame Ascendant',
    description: 'Command over fire and heat.',
    kind: 'major',
    codex_entry_id: null,
  },
];

/** Minimal mock effect_summary (#2898) — shared by every technique fixture below. */
export const mockTechniqueEffectSummary: TechniqueEffectSummary = {
  relationship: 'enemy',
  hostile: false,
  target_type: 'single',
  reach: 'same',
  reach_hops: 0,
  arena: 'physical',
  anima_cost: 5,
  applies: [],
  removes: [],
  damage: [],
  grants: [],
  summary: 'Cast on an enemy, in melee range, in the physical arena. Costs 5 anima.',
  is_underspecified: false,
};

export const mockCGTechniqueOptionPool: CGTechniqueOption = {
  id: 10,
  name: 'Shadow Strike',
  description: 'A strike drawn from the dark.',
  category: 'attack',
  codex_entry_id: null,
  is_tradition_technique: false,
  effect_summary: mockTechniqueEffectSummary,
};

export const mockCGTechniqueOptionSignature: CGTechniqueOption = {
  id: 11,
  name: 'Veil of Whispers',
  description: 'A signature technique of the tradition.',
  category: 'utility',
  codex_entry_id: 20,
  is_tradition_technique: true,
  effect_summary: mockTechniqueEffectSummary,
};

export const mockCGTechniqueOptions: CGTechniqueOption[] = [
  mockCGTechniqueOptionPool,
  mockCGTechniqueOptionSignature,
  {
    id: 12,
    name: 'Umbral Wall',
    description: 'A shielding wall of shadow.',
    category: 'defense',
    codex_entry_id: null,
    is_tradition_technique: false,
    effect_summary: mockTechniqueEffectSummary,
  },
];

/**
 * Minimal CodexEntryDetail for seeding `useCodexEntry`'s query cache in tests.
 * `CodexTerm`/`CodexModal` mount unconditionally whenever a gift/technique
 * carries a `codex_entry_id` (the entry fetch isn't gated on the modal being
 * open), so any test rendering a card with a non-null `codex_entry_id` must
 * seed `codexKeys.entry(id)` — otherwise it fires a real (failing) network
 * fetch in jsdom.
 */
export function mockCodexEntry(id: number): CodexEntryDetail {
  return {
    id,
    name: `Codex Entry ${id}`,
    summary: 'A lore entry.',
    is_public: true,
    is_featured: false,
    featured_order: null,
    subject: 1,
    subject_name: 'Test Subject',
    subject_path: [],
    display_order: 0,
    knowledge_status: 'known',
    known_by: [],
    lore_content: 'Lore content.',
    mechanics_content: null,
    lore_links: [],
    mechanics_links: [],
    learn_threshold: 0,
    research_progress: null,
    art_url: null,
    perspective_of: null,
    also_filed_under: [],
  };
}

// =============================================================================
// CG Explanations
// =============================================================================

export const mockCGExplanations: Record<string, string> = {
  origin_heading: 'Where does the story begin?',
  origin_intro: "Select the city or region where your character's story begins.",
  origin_lore_intro: 'You are one of the Gifted.',
  heritage_heading: 'Heritage',
  heritage_intro: "Define your character's beginnings, species, and identity.",
  heritage_beginnings_heading: 'Beginnings',
  heritage_beginnings_desc: 'Choose how your character entered the world.',
  heritage_species_heading: 'Species',
  heritage_species_desc: "Select your character's species.",
  heritage_gender_heading: 'Gender',
  heritage_cg_points_explanation: 'CG points are spent on character options.',
  lineage_heading: 'Lineage',
  lineage_intro: "Choose your character's family.",
  upbringing_heading: 'Your Upbringing',
  upbringing_intro: 'Choose how you were raised, then settle your family.',
  family_path_heading: 'Your Family',
  distinctions_heading: 'Distinctions',
  distinctions_intro: 'Select advantages and disadvantages.',
  distinctions_budget_explanation: 'Balance your distinction budget.',
  path_heading: 'Choose Your Path',
  path_intro: "Select your character's class and path.",
  path_skills_heading: 'Skills',
  path_skills_desc: 'Customize your skill selections.',
  attributes_heading: 'Attributes',
  attributes_intro: 'Allocate your primary statistics.',
  attributes_bonus_explanation: 'Bonuses from species and distinctions.',
  magic_heading: 'Magic',
  magic_intro: 'Configure your magical abilities.',
  magic_gift_heading: 'Gift',
  magic_gift_desc: 'Select your magical gift.',
  magic_anima_heading: 'Anima Ritual',
  magic_anima_desc: 'Define your anima recovery ritual.',
  magic_motif_heading: 'Motif',
  magic_motif_desc: 'Choose your magical motif.',
  magic_glimpse_heading: 'Glimpse',
  magic_glimpse_desc: 'Describe your magical glimpse.',
  appearance_heading: 'Appearance',
  appearance_intro: "Define your character's physical appearance.",
  identity_heading: 'Identity',
  identity_intro: "Define your character's name and story.",
  finaltouches_heading: 'Final Touches',
  finaltouches_intro: 'Add any finishing details.',
  review_heading: 'Review & Submit',
  review_intro: 'Review your character before submitting for approval.',
  review_xp_explanation: 'Unspent CG points convert to bonus XP.',
  arrival_title: 'Creating a Character and Starting their Story',
  arrival_intro:
    'You will be creating one of the Gifted, those who carry magic in their blood and ' +
    'have caught their first Glimpse of who one day they might become.',
  arrival_door: 'Begin',
  arrival_quiet: 'Return to the Hall',
};
