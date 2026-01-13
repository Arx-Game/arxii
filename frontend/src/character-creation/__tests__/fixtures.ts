/**
 * Character Creation Test Fixtures
 *
 * Mock data for testing character creation flows.
 */

import type {
  CharacterDraft,
  DraftData,
  Family,
  SpecialHeritage,
  Species,
  SpeciesOption,
  Stage,
  StartingArea,
} from '../types';

// =============================================================================
// Starting Areas
// =============================================================================

export const mockSpecialHeritage: SpecialHeritage = {
  id: 1,
  name: 'Fae-Touched',
  description: 'Born with a connection to the fae realms.',
  allows_full_species_list: true,
  family_display: 'Unknown Lineage',
};

export const mockStartingArea: StartingArea = {
  id: 1,
  name: 'Arx City',
  description: 'The great capital city, a hub of politics and intrigue.',
  crest_image: '/images/arx-crest.png',
  is_accessible: true,
  special_heritages: [mockSpecialHeritage],
};

export const mockStartingAreaNoHeritages: StartingArea = {
  id: 2,
  name: 'Northern Reaches',
  description: 'A cold, frontier region.',
  crest_image: null,
  is_accessible: true,
  special_heritages: [],
};

export const mockStartingAreaInaccessible: StartingArea = {
  id: 3,
  name: 'Hidden Vale',
  description: 'A secret location accessible only to trusted players.',
  crest_image: null,
  is_accessible: false,
  special_heritages: [],
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
};

export const mockSpeciesElf: Species = {
  id: 2,
  name: 'Elf',
  description: 'Long-lived and graceful beings.',
};

export const mockSpeciesDwarf: Species = {
  id: 3,
  name: 'Dwarf',
  description: 'Stout and hardy folk.',
};

export const mockSpeciesList: Species[] = [mockSpeciesHuman, mockSpeciesElf, mockSpeciesDwarf];

// =============================================================================
// Species Options (with CG costs)
// =============================================================================

export const mockSpeciesOptionHuman: SpeciesOption = {
  id: 1,
  species: mockSpeciesHuman,
  starting_area: mockStartingArea,
  cg_point_cost: 0,
  description_override: 'Humans from Arx are the most populous species.',
  stat_bonuses: { strength: 1 },
  starting_languages: [1],
  trust_required: 0,
  is_available: true,
  is_accessible: true,
};

export const mockSpeciesOptionElf: SpeciesOption = {
  id: 2,
  species: mockSpeciesElf,
  starting_area: mockStartingArea,
  cg_point_cost: 20,
  description_override: 'Elves in Arx are rare and graceful.',
  stat_bonuses: { dexterity: 1, mana: 2 },
  starting_languages: [1, 2],
  trust_required: 0,
  is_available: true,
  is_accessible: true,
};

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
// Draft Data
// =============================================================================

export const mockEmptyDraftData: DraftData = {};

export const mockCompleteDraftData: DraftData = {
  first_name: 'Testchar',
  description: 'A tall figure with piercing eyes.',
  personality: 'Bold and adventurous.',
  background: 'Born to humble origins but destined for greatness.',
  attributes_complete: true,
  path_skills_complete: true,
  traits_complete: true,
};

// =============================================================================
// Character Drafts
// =============================================================================

export const mockEmptyDraft: CharacterDraft = {
  id: 1,
  current_stage: 1 as Stage,
  selected_area: null,
  selected_heritage: null,
  selected_species_option: null,
  species: '',
  selected_gender: null,
  gender: '',
  pronoun_subject: '',
  pronoun_object: '',
  pronoun_possessive: '',
  age: null,
  family: null,
  is_orphan: false,
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
  } as Record<Stage, boolean>,
};

export const mockDraftWithArea: CharacterDraft = {
  ...mockEmptyDraft,
  id: 2,
  selected_area: mockStartingArea,
  stage_completion: {
    ...mockEmptyDraft.stage_completion,
    1: true,
  } as Record<Stage, boolean>,
};

export const mockDraftWithHeritage: CharacterDraft = {
  ...mockDraftWithArea,
  id: 3,
  current_stage: 2 as Stage,
  selected_heritage: mockSpecialHeritage,
  species: 'Human',
  selected_gender: { id: 2, key: 'female', display_name: 'Female' },
  gender: 'female',
  pronoun_subject: 'she',
  pronoun_object: 'her',
  pronoun_possessive: 'hers',
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
  selected_heritage: null,
  selected_species_option: mockSpeciesOptionElf,
  family: mockNobleFamily,
  cg_points_spent: 20,
  cg_points_remaining: 80,
  stat_bonuses: { dexterity: 1, mana: 2 },
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
  current_stage: 8 as Stage,
  draft_data: mockCompleteDraftData,
  stage_completion: {
    1: true,
    2: true,
    3: true,
    4: true,
    5: true,
    6: true,
    7: true,
    8: true,
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
    8: false,
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
