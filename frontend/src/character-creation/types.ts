/**
 * Character Creation types
 */

export interface StartingArea {
  id: number;
  name: string;
  description: string;
  crest_image: string | null;
  is_accessible: boolean;
  realm_theme: string;
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
  xp_conversion_rate: number;
  is_active: boolean;
}

export interface CGPointsBreakdown {
  starting_budget: number;
  spent: number;
  remaining: number;
  xp_conversion_rate: number;
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

// =============================================================================
// Tarot Card Types
// =============================================================================

export interface TarotCard {
  id: number;
  name: string;
  arcana_type: 'major' | 'minor';
  suit: 'swords' | 'cups' | 'wands' | 'coins' | null;
  rank: number;
  latin_name: string;
  description: string;
  surname_upright: string;
  surname_reversed: string;
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
  DISTINCTIONS = 4,
  PATH_SKILLS = 5,
  ATTRIBUTES = 6,
  MAGIC = 7,
  APPEARANCE = 8,
  IDENTITY = 9,
  FINAL_TOUCHES = 10,
  REVIEW = 11,
}

export const STAGE_LABELS: Record<Stage, string> = {
  [Stage.ORIGIN]: 'Origin',
  [Stage.HERITAGE]: 'Heritage',
  [Stage.LINEAGE]: 'Lineage',
  [Stage.DISTINCTIONS]: 'Distinctions',
  [Stage.PATH_SKILLS]: 'Path & Skills',
  [Stage.ATTRIBUTES]: 'Attributes',
  [Stage.MAGIC]: 'Magic',
  [Stage.APPEARANCE]: 'Appearance',
  [Stage.IDENTITY]: 'Identity',
  [Stage.FINAL_TOUCHES]: 'Final Touches',
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
  selected_tradition: Tradition | null;
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

/**
 * Magical tradition — how a character learned magic.
 * From /api/character-creation/traditions/?beginning_id=N
 */
export interface Tradition {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  sort_order: number;
  codex_entry_ids: number[];
  required_distinction_id: number | null;
}

// =============================================================================
// NEW Magic System Types (Build-Your-Own)
// =============================================================================

/**
 * Technique style (how magic manifests).
 * From /api/magic/technique-styles/
 */
export interface TechniqueStyle {
  id: number;
  name: string;
  description: string;
}

/**
 * Effect type (what the technique does).
 * From /api/magic/effect-types/
 */
export interface EffectType {
  id: number;
  name: string;
  description: string;
  base_power: number | null;
  base_anima_cost: number;
  has_power_scaling: boolean;
}

/**
 * Restriction that grants power bonuses.
 * From /api/magic/restrictions/
 */
export interface Restriction {
  id: number;
  name: string;
  description: string;
  power_bonus: number;
  allowed_effect_type_ids: number[];
}

/**
 * Resonance association for motif customization.
 * From /api/magic/resonance-associations/
 */
export interface ResonanceAssociation {
  id: number;
  name: string;
  description: string;
  category: string;
}

/**
 * Facet - hierarchical imagery/symbolism for motifs.
 * From /api/magic/facets/
 */
export interface Facet {
  id: number;
  name: string;
  description: string;
  parent: number | null;
  parent_name: string | null;
  depth: number;
  full_path: string;
}

/**
 * Facet tree node with nested children.
 * From /api/magic/facets/tree/
 */
export interface FacetTreeNode {
  id: number;
  name: string;
  description: string;
  children: FacetTreeNode[];
}

/**
 * Draft facet assignment for character creation.
 */
export interface DraftFacetAssignment {
  id: number;
  motif_resonance: number;
  facet: number;
}

/**
 * A built technique within a gift.
 */
export interface Technique {
  id: number;
  name: string;
  gift: number;
  style: number;
  effect_type: number;
  restriction_ids: number[];
  level: number;
  anima_cost: number;
  description: string;
  calculated_power: number;
  tier: number;
}

/**
 * NEW Gift type for build-your-own system.
 * Replaces the old Gift that had powers and level_requirement.
 */
export interface GiftDetail {
  id: number;
  name: string;
  affinity_breakdown: Record<string, number>;
  description: string;
  resonances: Resonance[];
  resonance_ids: number[];
  techniques: Technique[];
  technique_count: number;
}

/**
 * Lightweight gift for list views.
 */
export interface GiftListItemNew {
  id: number;
  name: string;
  affinity_breakdown: Record<string, number>;
  description: string;
  technique_count: number;
}

// =============================================================================
// Draft Models for Character Creation Magic Stage
// =============================================================================

/**
 * Draft gift being designed during character creation.
 */
export interface DraftGift {
  id: number;
  name: string;
  resonances: number[];
  description: string;
  techniques: DraftTechnique[];
  affinity_breakdown: Record<string, number>;
}

/**
 * Draft technique within a draft gift.
 */
export interface DraftTechnique {
  id: number;
  gift: number;
  name: string;
  style: number;
  effect_type: number;
  restrictions: number[];
  level: number;
  description: string;
  calculated_power: number | null;
}

/**
 * Draft motif with resonances during character creation.
 */
export interface DraftMotif {
  id: number;
  description: string;
  resonances: DraftMotifResonance[];
}

/**
 * Draft motif resonance with facet assignments.
 */
export interface DraftMotifResonance {
  id: number;
  resonance: number;
  is_from_gift: boolean;
  facet_assignments: DraftFacetAssignment[];
}

/**
 * Draft anima ritual during CG (freeform stat+skill+resonance).
 * Replaces old AnimaRitualType selection.
 */
export interface DraftAnimaRitual {
  id: number;
  stat: number;
  stat_name: string;
  skill: number;
  skill_name: string;
  specialization: number | null;
  specialization_name: string | null;
  resonance: number;
  resonance_name: string;
  description: string;
}

/**
 * Association attached to a motif resonance.
 */
export interface MotifResonanceAssociation {
  id: number;
  association: number;
  association_name: string;
}

/**
 * Motif resonance with associations.
 */
export interface MotifResonance {
  id: number;
  resonance: number;
  resonance_name: string;
  is_from_gift: boolean;
  associations: MotifResonanceAssociation[];
}

/**
 * Character's magical motif with resonances.
 */
export interface Motif {
  id: number;
  description: string;
  resonances: MotifResonance[];
}

// =============================================================================
// Modifier Type Items (Affinities & Resonances via /api/mechanics/types/)
// =============================================================================

/**
 * ModifierType record from /api/mechanics/types/?category=affinity|resonance.
 * Replaces the legacy Affinity and Resonance interfaces.
 */
export interface ModifierTypeItem {
  id: number;
  name: string;
  category: number;
  category_name: string;
  description: string;
  display_order: number;
  is_active: boolean;
  opposite: number | null;
  resonance_affinity: string | null;
}

export type Affinity = ModifierTypeItem;
export type Resonance = ModifierTypeItem;

/**
 * Projected resonance total from draft distinctions.
 * From /api/character-creation/drafts/{id}/projected-resonances/
 */
export interface ProjectedResonance {
  resonance_id: number;
  resonance_name: string;
  total: number;
  sources: Array<{
    distinction_name: string;
    value: number;
  }>;
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

  // NEW: Draft gift being designed (stored in DraftGift model)
  draft_gift_id?: number;

  // NEW: Draft techniques being built (stored in DraftTechnique models)
  draft_technique_ids?: number[];

  // NEW: Draft anima ritual (stat + skill + resonance)
  draft_ritual_stat_id?: number;
  draft_ritual_skill_id?: number;
  draft_ritual_specialization_id?: number | null;
  draft_ritual_resonance_id?: number;
  draft_ritual_description?: string;

  // NEW: Motif associations selected for each resonance
  motif_associations?: Record<number, number[]>; // resonance_id -> association_ids

  // The Glimpse story (optional, can be filled later)
  glimpse_story?: string;

  // Completion flag
  magic_complete?: boolean;
}

export interface DraftGoal {
  domain_id: number;
  notes: string;
  points: number;
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
  // Skills - maps skill ID to value (0, 10, 20, 30)
  skills?: Record<string, number>;
  // Specializations - maps specialization ID to value (0, 10, 20, 30)
  specializations?: Record<string, number>;
  // Magic fields - Aura distribution
  aura_celestial?: number;
  aura_primal?: number;
  aura_abyssal?: number;
  // Magic fields - Legacy (kept for backwards compatibility)
  selected_gift_id?: number;
  selected_resonance_ids?: number[];
  selected_ritual_type_id?: number;
  anima_ritual_description?: string;
  // Magic fields - New build-your-own system
  draft_gift_id?: number;
  draft_ritual_stat_id?: number;
  draft_ritual_skill_id?: number;
  draft_ritual_specialization_id?: number | null;
  draft_ritual_resonance_id?: number;
  draft_ritual_description?: string;
  // The Glimpse story
  glimpse_story?: string;
  magic_complete?: boolean;
  // Tarot card selection for familyless characters
  tarot_card_id?: number;
  tarot_reversed?: boolean;
  // Goals for Final Touches stage
  goals?: DraftGoal[];
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
  selected_tradition_id?: number | null;
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

// === Application Review System Types ===

export type ApplicationStatus =
  | 'submitted'
  | 'in_review'
  | 'revisions_requested'
  | 'approved'
  | 'denied'
  | 'withdrawn';

export type CommentType = 'message' | 'status_change';

export interface ApplicationComment {
  id: number;
  author: number | null;
  author_name: string | null;
  text: string;
  comment_type: CommentType;
  created_at: string;
}

export interface DraftApplication {
  id: number;
  draft: number;
  draft_name: string;
  player_name: string;
  status: ApplicationStatus;
  submitted_at: string;
  reviewer: number | null;
  reviewer_name: string | null;
  reviewed_at: string | null;
  submission_notes: string;
  expires_at: string | null;
}

export interface DraftApplicationDetail extends DraftApplication {
  comments: ApplicationComment[];
  draft_summary: DraftSummary;
}

export interface DraftSummary {
  id: number;
  first_name: string;
  description: string;
  personality: string;
  background: string;
  species: string | null;
  area: string | null;
  beginnings: string | null;
  family: string | null;
  gender: string | null;
  age: number | null;
  stage_completion: Record<number, boolean>;
}
