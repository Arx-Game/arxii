/**
 * Character Creation types
 */

export interface StartingArea {
  id: number;
  name: string;
  description: string;
  crest_image: string | null;
  is_accessible: boolean;
  special_heritages: SpecialHeritage[];
}

export interface SpecialHeritage {
  id: number;
  name: string;
  description: string;
  allows_full_species_list: boolean;
  family_display: string;
}

export interface Species {
  id: number;
  name: string;
  description: string;
}

export interface SpeciesOption {
  id: number;
  species: Species;
  starting_area: StartingArea;
  cg_point_cost: number;
  description_override: string;
  stat_bonuses: Record<string, number>;
  starting_languages: number[];
  trust_required: number;
  is_available: boolean;
  is_accessible: boolean;
}

export interface CGPointBudget {
  id: number;
  name: string;
  starting_points: number;
  is_active: boolean;
}

export interface CGPointsBreakdown {
  starting_budget: number;
  spent: number;
  remaining: number;
  breakdown: Array<{
    category: string;
    item: string;
    cost: number;
  }>;
}

export interface Family {
  id: number;
  name: string;
  family_type: 'commoner' | 'noble';
  description: string;
  origin_realm?: number;
}

export interface FamilyMember {
  id: number;
  family: Family;
  family_id: number;
  member_type: 'character' | 'placeholder' | 'npc';
  character: number | null;
  character_name: string | null;
  display_name: string;
  name: string;
  description: string;
  age: number | null;
  created_by: number;
  created_at: string;
}

export interface FamilyRelationship {
  id: number;
  from_member: number;
  to_member: number;
  relationship_type:
    | 'parent'
    | 'child'
    | 'sibling'
    | 'spouse'
    | 'aunt_uncle'
    | 'niece_nephew'
    | 'cousin'
    | 'grandparent'
    | 'grandchild';
  notes: string;
}

export interface FamilyTree {
  id: number;
  name: string;
  family_type: 'commoner' | 'noble';
  description: string;
  origin_realm: number | null;
  members: FamilyMember[];
  relationships: FamilyRelationship[];
  open_positions_count: number;
}

export type Gender = 'male' | 'female' | 'nonbinary' | 'other';

export interface Pronouns {
  subject: string;
  object: string;
  possessive: string;
}

export const DEFAULT_PRONOUNS: Record<Gender, Pronouns> = {
  male: { subject: 'he', object: 'him', possessive: 'his' },
  female: { subject: 'she', object: 'her', possessive: 'hers' },
  nonbinary: { subject: 'they', object: 'them', possessive: 'theirs' },
  other: { subject: 'they', object: 'them', possessive: 'theirs' },
};

export enum Stage {
  ORIGIN = 1,
  HERITAGE = 2,
  LINEAGE = 3,
  ATTRIBUTES = 4,
  PATH_SKILLS = 5,
  TRAITS = 6,
  IDENTITY = 7,
  REVIEW = 8,
}

export const STAGE_LABELS: Record<Stage, string> = {
  [Stage.ORIGIN]: 'Origin',
  [Stage.HERITAGE]: 'Heritage',
  [Stage.LINEAGE]: 'Lineage',
  [Stage.ATTRIBUTES]: 'Attributes',
  [Stage.PATH_SKILLS]: 'Path & Skills',
  [Stage.TRAITS]: 'Traits',
  [Stage.IDENTITY]: 'Identity',
  [Stage.REVIEW]: 'Review',
};

export interface CharacterDraft {
  id: number;
  current_stage: Stage;
  selected_area: StartingArea | null;
  selected_heritage: SpecialHeritage | null;
  selected_species_option: SpeciesOption | null;
  species: string; // DEPRECATED - use selected_species_option
  selected_gender: { id: number; key: string; display_name: string } | null;
  gender: Gender | ''; // DEPRECATED - use selected_gender
  pronoun_subject: string;
  pronoun_object: string;
  pronoun_possessive: string;
  age: number | null;
  family: Family | null;
  is_orphan: boolean;
  cg_points_spent: number;
  cg_points_remaining: number;
  stat_bonuses: Record<string, number>;
  draft_data: DraftData;
  stage_completion: Record<Stage, boolean>;
}

export interface Stats {
  strength: number;
  agility: number;
  stamina: number;
  charm: number;
  presence: number;
  intellect: number;
  wits: number;
  willpower: number;
}

export interface DraftData {
  first_name?: string;
  description?: string;
  personality?: string;
  background?: string;
  stats?: Stats;
  attributes_complete?: boolean;
  path_skills_complete?: boolean;
  traits_complete?: boolean;
  [key: string]: unknown;
}

export interface CharacterDraftUpdate {
  current_stage?: Stage;
  selected_area_id?: number | null;
  selected_heritage_id?: number | null;
  selected_species_option_id?: number | null;
  selected_gender_id?: number | null;
  species?: string; // DEPRECATED
  gender?: Gender | ''; // DEPRECATED
  pronoun_subject?: string;
  pronoun_object?: string;
  pronoun_possessive?: string;
  age?: number | null;
  family_id?: number | null;
  is_orphan?: boolean;
  draft_data?: Partial<DraftData>;
}

/**
 * Get default stat values for character creation.
 * All stats start at 2 (20 internal) during character creation.
 */
export function getDefaultStats(): Stats {
  return {
    strength: 20,
    agility: 20,
    stamina: 20,
    charm: 20,
    presence: 20,
    intellect: 20,
    wits: 20,
    willpower: 20,
  };
}

/**
 * Calculate free points remaining from stat allocations.
 *
 * Budget:
 * - Base: 8 stats × 2 = 16 points
 * - Free: 5 points
 * - Total: 21 points
 *
 * Current spend: sum(stats.values()) / 10 (stats stored as 10-50, displayed as 1-5)
 * Remaining: 21 - spent
 */
export function calculateFreePoints(stats: Stats): number {
  const STARTING_BUDGET = 21;
  const spent = Math.floor(Object.values(stats).reduce((sum, val) => sum + val, 0) / 10);
  return STARTING_BUDGET - spent;
}
