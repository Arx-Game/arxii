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
  Family,
  HeightBand,
  Species,
  Stage,
  StartingArea,
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
};

export const mockStartingAreaNoHeritages: StartingArea = {
  id: 2,
  name: 'Northern Reaches',
  description: 'A cold, frontier region.',
  crest_image: null,
  is_accessible: true,
};

export const mockStartingAreaInaccessible: StartingArea = {
  id: 3,
  name: 'Hidden Vale',
  description: 'A secret location accessible only to trusted players.',
  crest_image: null,
  is_accessible: false,
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
  selected_beginnings: null,
  selected_species: null,
  selected_gender: null,
  age: null,
  family: null,
  is_orphan: false,
  height_band: null,
  height_inches: null,
  build: null,
  selected_path: null,
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
  } as Record<Stage, boolean>,
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
  current_stage: 10 as Stage,
  height_band: mockHeightBandAverage,
  height_inches: 68,
  build: mockBuildAverage,
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
    9: true,
    10: true,
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
    10: false,
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
