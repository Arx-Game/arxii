/**
 * Character Creation types
 */

export interface StartingArea {
  id: number;
  name: string;
  description: string;
  crest_image: string | null;
  is_accessible: boolean;
}

export interface Beginnings {
  id: number;
  name: string;
  description: string;
  art_image: string | null;
  family_known: boolean;
  allowed_species_ids: number[];
  grants_species_languages: boolean;
  cg_point_cost: number;
  is_accessible: boolean;
}

export interface Species {
  id: number;
  name: string;
  description: string;
  parent?: number | null;
  parent_name?: string | null;
  stat_bonuses: Record<string, number>;
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
  mother: number | null;
  mother_id?: number | null;
  father: number | null;
  father_id?: number | null;
  relationship_to_root: string | null;
  created_by: number;
  created_at: string;
}

export interface FamilyTree {
  id: number;
  name: string;
  family_type: 'commoner' | 'noble';
  description: string;
  origin_realm: number | null;
  members: FamilyMember[];
  open_positions_count: number;
}

export type Gender = 'male' | 'female' | 'nonbinary' | 'other';

export interface GenderOption {
  id: number;
  key: string;
  display_name: string;
}

/**
 * Skill specialization definition.
 */
export interface Specialization {
  id: number;
  name: string;
  description: string;
  tooltip: string;
  display_order: number;
  is_active: boolean;
  parent_skill_id: number;
  parent_skill_name: string;
}

/**
 * Skill definition with specializations.
 */
export interface Skill {
  id: number;
  name: string;
  category: string;
  category_display: string;
  description: string;
  tooltip: string;
  display_order: number;
  is_active: boolean;
  specializations: Specialization[];
}

/**
 * Lighter skill definition without specializations (for list views).
 */
export interface SkillListItem {
  id: number;
  name: string;
  category: string;
  category_display: string;
  tooltip: string;
  display_order: number;
  is_active: boolean;
}

/**
 * Skill point budget configuration for CG.
 */
export interface SkillPointBudget {
  id: number;
  path_points: number;
  free_points: number;
  total_points: number;
  points_per_tier: number;
  specialization_unlock_threshold: number;
  max_skill_value: number;
  max_specialization_value: number;
}

/**
 * Path skill suggestion for CG.
 * Suggested skill allocations that players can freely redistribute.
 */
export interface PathSkillSuggestion {
  id: number;
  path_id: number;
  path_name: string;
  skill_id: number;
  skill_name: string;
  skill_category: string;
  suggested_value: number;
  display_order: number;
}

/**
 * Character path definition.
 * Paths are the narrative-focused class system for Arx II.
 */
export interface Path {
  id: number;
  name: string;
  description: string;
  stage: number; // 1=Prospect, 2=Potential, 3=Puissant, etc.
  minimum_level: number;
  icon_url: string | null;
  icon_name: string; // Lucide icon name (e.g., 'swords', 'eye')
  aspects: string[]; // Aspect names only (weights are staff-only)
  skill_suggestions?: PathSkillSuggestion[];
}

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

export interface HeightBand {
  id: number;
  name: string;
  display_name: string;
  min_inches: number;
  max_inches: number;
  is_cg_selectable: boolean;
}

export interface Build {
  id: number;
  name: string;
  display_name: string;
  is_cg_selectable: boolean;
}

export interface FormTraitOption {
  id: number;
  name: string;
  display_name: string;
  sort_order: number;
}

export interface FormTrait {
  id: number;
  name: string;
  display_name: string;
  trait_type: 'color' | 'style';
}

export interface FormTraitWithOptions {
  trait: FormTrait;
  options: FormTraitOption[];
}

export enum Stage {
  ORIGIN = 1,
  HERITAGE = 2,
  LINEAGE = 3,
  ATTRIBUTES = 4,
  PATH_SKILLS = 5,
  DISTINCTIONS = 6,
  MAGIC = 7,
  APPEARANCE = 8,
  IDENTITY = 9,
  REVIEW = 10,
}

export const STAGE_LABELS: Record<Stage, string> = {
  [Stage.ORIGIN]: 'Origin',
  [Stage.HERITAGE]: 'Heritage',
  [Stage.LINEAGE]: 'Lineage',
  [Stage.ATTRIBUTES]: 'Attributes',
  [Stage.PATH_SKILLS]: 'Path & Skills',
  [Stage.DISTINCTIONS]: 'Distinctions',
  [Stage.MAGIC]: 'Magic',
  [Stage.APPEARANCE]: 'Appearance',
  [Stage.IDENTITY]: 'Identity',
  [Stage.REVIEW]: 'Review',
};

export interface CharacterDraft {
  id: number;
  current_stage: Stage;
  selected_area: StartingArea | null;
  selected_beginnings: Beginnings | null;
  selected_species: Species | null;
  selected_gender: { id: number; key: string; display_name: string } | null;
  age: number | null;
  family: Family | null;
  is_orphan: boolean;
  height_band: HeightBand | null;
  height_inches: number | null;
  build: Build | null;
  selected_path: Path | null;
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
  perception: number;
  intellect: number;
  wits: number;
  willpower: number;
}

/**
 * Stat definition from the backend API.
 */
export interface StatDefinition {
  id: number;
  name: string;
  trait_type: string;
  category: string;
  description: string;
}

// =============================================================================
// Magic System Types
// =============================================================================

/**
 * The three fundamental affinity types in the magic system.
 */
export const AFFINITY_TYPES = ['celestial', 'primal', 'abyssal'] as const;
export type AffinityType = (typeof AFFINITY_TYPES)[number];

export interface Affinity {
  id: number;
  affinity_type: AffinityType;
  name: string;
  description: string;
}

export interface Resonance {
  id: number;
  name: string;
  slug: string;
  default_affinity: number;
  default_affinity_name: string;
  description: string;
}

export interface Gift {
  id: number;
  name: string;
  slug: string;
  affinity: number;
  affinity_name: string;
  description: string;
  level_requirement: number;
  resonances: Resonance[];
  powers: Power[];
}

export interface GiftListItem {
  id: number;
  name: string;
  slug: string;
  affinity: number;
  affinity_name: string;
  description: string;
  level_requirement: number;
  power_count: number;
}

export interface Power {
  id: number;
  name: string;
  slug: string;
  gift: number;
  affinity: number;
  affinity_name: string;
  base_intensity: number;
  base_control: number;
  anima_cost: number;
  level_requirement: number;
  description: string;
  resonances: Resonance[];
}

export interface AnimaRitualType {
  id: number;
  name: string;
  slug: string;
  category: 'solitary' | 'collaborative' | 'environmental' | 'ceremonial';
  category_display: string;
  description: string;
  base_recovery: number;
}

/**
 * Magic selections stored in draft_data during character creation.
 */
export interface MagicDraftData {
  // Aura distribution (must sum to 100)
  aura_celestial?: number;
  aura_primal?: number;
  aura_abyssal?: number;
  // Selected gift
  selected_gift_id?: number;
  // Personal resonances (array of resonance IDs)
  selected_resonance_ids?: number[];
  // Anima ritual
  selected_ritual_type_id?: number;
  anima_ritual_description?: string;
  // The Glimpse story (optional, can be filled later)
  glimpse_story?: string;
  // Completion flag
  magic_complete?: boolean;
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
  // Appearance - form traits (hair color, eye color, etc.)
  form_traits?: Record<string, number>;
  // Magic fields
  aura_celestial?: number;
  aura_primal?: number;
  aura_abyssal?: number;
  selected_gift_id?: number;
  selected_resonance_ids?: number[];
  selected_ritual_type_id?: number;
  anima_ritual_description?: string;
  glimpse_story?: string;
  magic_complete?: boolean;
  [key: string]: unknown;
}

export interface CharacterDraftUpdate {
  current_stage?: Stage;
  selected_area_id?: number | null;
  selected_beginnings_id?: number | null;
  selected_species_id?: number | null;
  selected_gender_id?: number | null;
  age?: number | null;
  family_id?: number | null;
  is_orphan?: boolean;
  height_band_id?: number | null;
  height_inches?: number | null;
  build_id?: number | null;
  selected_path_id?: number | null;
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
    perception: 20,
    intellect: 20,
    wits: 20,
    willpower: 20,
  };
}

/**
 * Calculate free points remaining from stat allocations.
 *
 * Budget:
 * - Base: 9 stats × 2 = 18 points
 * - Free: 5 points
 * - Total: 23 points
 *
 * Current spend: sum(stats.values()) / 10 (stats stored as 10-50, displayed as 1-5)
 * Remaining: 23 - spent
 */
export function calculateFreePoints(stats: Stats): number {
  const STARTING_BUDGET = 23;
  const spent = Math.floor(Object.values(stats).reduce((sum, val) => sum + val, 0) / 10);
  return STARTING_BUDGET - spent;
}
