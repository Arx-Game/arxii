/**
 * Character Creation Test Fixtures
 *
 * Mock data for testing character creation flows.
 */

import type {
  Beginnings,
  Build,
  CharacterDraft,
  DraftData,
  DraftGift,
  DraftTechnique,
  EffectType,
  Family,
  GiftDetail,
  HeightBand,
  Resonance,
  ResonanceAssociation,
  Restriction,
  Species,
  Stage,
  StartingArea,
  Technique,
  TechniqueStyle,
} from '../types';

// =============================================================================
// Beginnings
// =============================================================================

export const mockBeginnings: Beginnings = {
  id: 1,
  name: 'Normal Upbringing',
  description: 'Raised in the city with a conventional background.',
  art_image: null,
  family_known: true,
  allowed_species_ids: [1, 2],
  grants_species_languages: true,
  cg_point_cost: 0,
  is_accessible: true,
};

export const mockBeginningsUnknownFamily: Beginnings = {
  id: 2,
  name: 'Sleeper',
  description: 'Awakened from magical slumber with no memory of origins.',
  art_image: null,
  family_known: false,
  allowed_species_ids: [1, 2, 3],
  grants_species_languages: false,
  cg_point_cost: 0,
  is_accessible: true,
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
};

export const mockSpeciesElf: Species = {
  id: 2,
  name: 'Elf',
  description: 'Long-lived and graceful beings.',
  stat_bonuses: { agility: 1, intellect: 1 },
};

export const mockSpeciesDwarf: Species = {
  id: 3,
  name: 'Dwarf',
  description: 'Stout and hardy folk.',
  stat_bonuses: { stamina: 1, willpower: 1 },
};

export const mockSpeciesList: Species[] = [mockSpeciesHuman, mockSpeciesElf, mockSpeciesDwarf];

// =============================================================================
// Families
// =============================================================================

export const mockNobleFamily: Family = {
  id: 1,
  name: 'Valardin',
  family_type: 'noble',
  description: 'An honorable noble house known for martial prowess.',
};

export const mockNobleFamily2: Family = {
  id: 2,
  name: 'Velenosa',
  family_type: 'noble',
  description: 'A cunning noble house with southern roots.',
};

export const mockCommonerFamily: Family = {
  id: 3,
  name: 'Smith',
  family_type: 'commoner',
  description: 'A common family of craftspeople.',
};

export const mockFamilies: Family[] = [mockNobleFamily, mockNobleFamily2, mockCommonerFamily];

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
  personality: 'Bold and adventurous.',
  background: 'Born to humble origins but destined for greatness.',
  concept: 'A warrior seeking redemption.',
  quote: 'The dawn comes for all.',
  path_skills_complete: true,
  traits_complete: true,
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
  age: null,
  family: null,
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
  magic_validation_errors: [],
  stage_errors: {},
  stats_free_points: 5,
  stats_max_free_points: 5,
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
    6: false, // incomplete
    7: true,
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
  },
];

export const mockTechnique: Technique = {
  id: 1,
  name: 'Shadow Strike',
  gift: 1,
  style: 1,
  effect_type: 1,
  restriction_ids: [1],
  level: 5,
  anima_cost: 2,
  description: 'A strike from the shadows',
  calculated_power: 25,
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
// Draft Magic Fixtures (for character creation)
// =============================================================================

export const mockDraftTechnique: DraftTechnique = {
  id: 1,
  gift: 1,
  name: 'Shadow Strike',
  style: 1,
  effect_type: 1,
  restrictions: [1],
  level: 5,
  description: 'A strike from the shadows',
  calculated_power: 25,
};

export const mockDraftGift: DraftGift = {
  id: 1,
  name: 'Whispers of Shadow',
  affinity_breakdown: { Abyssal: 2 },
  resonances: [1, 2],
  description: 'Mastery over shadows and darkness',
  techniques: [mockDraftTechnique],
};

// =============================================================================
// CG Explanations
// =============================================================================

export const mockCGExplanations: Record<string, string> = {
  origin_heading: 'Choose Your Origin',
  origin_intro: "Select the city or region where your character's story begins.",
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
};
