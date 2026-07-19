/**
 * Character Creation types
 */

// Single definition lives with the shared guided-flow component; both CG and
// the character sheet mount (Task 6) import it from here.
export type { GlimpseTagOption } from '@/magic/components/glimpse/glimpseTypes';

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
  codex_entry_ids: number[];
}

export interface Species {
  id: number;
  name: string;
  description: string;
  parent?: number | null;
  parent_name?: string | null;
  stat_bonuses: Record<string, number>;
  codex_entry_id: number | null;
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
  family_type: 'commoner' | 'noble' | 'crime';
  description: string;
  origin_realm?: number;
}

// Kinship graph payload (#2062): person-nodes + typed edges, viewer-filtered.
export interface KinNode {
  id: number;
  name: string;
  tier: string;
  family_id: number | null;
  is_deceased: boolean;
  is_appable: boolean;
  gender: string;
  age: number | null;
  description: string;
}

export interface KinParentageEdge {
  child_id: number;
  parent_id: number;
  kind: string;
  is_true: boolean;
  via_secret: boolean;
}

export interface KinUnionEdge {
  id: number;
  kind: string;
  member_ids: number[];
  ended: boolean;
}

export interface FamilyTree {
  family: Family;
  nodes: KinNode[];
  parentage: KinParentageEdge[];
  unions: KinUnionEdge[];
}

// Open app-in positions for a family (#2062 slot mountain).
export interface KinSlot {
  id: number;
  name: string;
  name_locked: boolean;
  description: string;
  age_min: number | null;
  age_max: number | null;
  allowed_genders: string[];
  family: number;
}

export interface KinSlotPool {
  id: number;
  family: number;
  description: string;
  count_remaining: number;
  age_min: number | null;
  age_max: number | null;
  allowed_genders: string[];
  parent_names: string[];
}

export interface FamilySlots {
  slots: KinSlot[];
  pools: KinSlotPool[];
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
  description_reversed: string;
  surname_upright: string;
  surname_reversed: string;
}

export interface NamingRitualConfig {
  flavor_text: string;
  codex_entry_id: number | null;
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
  codex_entry_ids: number[];
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
  PATH = 5,
  GIFT = 6,
  ATTRIBUTES = 7,
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
  [Stage.PATH]: 'Path',
  [Stage.GIFT]: 'Gift',
  [Stage.ATTRIBUTES]: 'Attributes & Skills',
  [Stage.APPEARANCE]: 'Appearance',
  [Stage.IDENTITY]: 'Identity',
  [Stage.FINAL_TOUCHES]: 'Final Touches',
  [Stage.REVIEW]: 'Review',
};

/** Reference shape from /api/worship/beings/ — never carries pools/avatars (#2355). */
export interface WorshippedBeingRef {
  id: number;
  name: string;
  tradition_name: string;
}

export interface CharacterDraft {
  id: number;
  current_stage: Stage;
  selected_area: StartingArea | null;
  selected_beginnings: Beginnings | null;
  selected_species: Species | null;
  selected_gender: { id: number; key: string; display_name: string } | null;
  age: number | null;
  family: Family | null;
  claimed_kin_slot: number | null;
  claimed_kin_pool: number | null;
  defer_parents: boolean;
  height_band: HeightBand | null;
  height_inches: number | null;
  build: Build | null;
  selected_path: Path | null;
  selected_tradition: Tradition | null;
  public_worship: WorshippedBeingRef | null;
  secret_worship: WorshippedBeingRef | null;
  cg_points_spent: number;
  cg_points_remaining: number;
  stat_bonuses: Record<string, number>;
  draft_data: DraftData;
  stage_completion: Record<Stage, boolean>;
  stage_errors: Partial<Record<Stage, string[]>>;
  has_existing_characters: boolean;
  stats_points_remaining: number;
  stats_budget: number;
  /** Gift-stage technique pick budget (base 1 + distinction bonus, #2426). */
  starting_technique_picks: number;
}

export interface Stats {
  // Physical
  strength: number;
  agility: number;
  stamina: number;
  // Social
  charm: number;
  presence: number;
  composure: number;
  // Mental
  intellect: number;
  wits: number;
  stability: number;
  // Meta
  luck: number;
  perception: number;
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
// CG Gift/Technique Option Types (GiftStage funnel, #2426 Task 10)
// =============================================================================

/**
 * Gift row for the CG gift-options list.
 * From GET /api/character-creation/gifts/?draft_id=<id>
 */
export interface CGGiftOption {
  id: number;
  name: string;
  description: string;
  kind: string;
  codex_entry_id: number | null;
}

/**
 * Technique row for the CG technique-options list (pool ∪ signature).
 * From GET /api/character-creation/technique-options/?draft_id=<id>&gift_id=<id>
 */
export interface CGTechniqueOption {
  id: number;
  name: string;
  description: string;
  category: 'attack' | 'defense' | 'buff' | 'debuff' | 'utility';
  codex_entry_id: number | null;
  is_signature: boolean;
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
  intensity: number;
  control: number;
  anima_cost: number;
  description: string;
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
  codex_entry_id: number | null;
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
  // Origin story guided flow (#2478)
  origin_slots?: Record<string, string>;
  concept?: string;
  quote?: string;
  stats?: Stats;
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
  // Magic fields - Gift/technique picks (GiftStage funnel, #2426 Task 10)
  selected_gift_id?: number | null;
  selected_technique_ids?: number[];
  // Magic fields - Anima Check (the stat + skill every cast rolls, #2426)
  anima_check_stat_id?: number | null;
  anima_check_skill_id?: number | null;
  anima_ritual_name?: string;
  motif_description?: string;
  // The Glimpse guided flow (#2427)
  glimpse_story?: string;
  glimpse_tag_ids?: number[];
  glimpse_linked_distinction_ids?: number[];
  // Magic fields - Gift resonance (anchors the latent GIFT thread at CG finalization, #1620)
  selected_gift_resonance_id?: number | null;
  magic_complete?: boolean;
  // Tarot card selection for familyless characters
  tarot_card_name?: string;
  tarot_reversed?: boolean;
  // Orphan / no family flag for lineage stage
  lineage_is_orphan?: boolean;
  // Goals for Final Touches stage
  goals?: DraftGoal[];
  [key: string]: unknown;
}

export interface CharacterDraftUpdate {
  claimed_kin_slot_id?: number | null;
  claimed_kin_pool_id?: number | null;
  defer_parents?: boolean;
  current_stage?: Stage;
  selected_area_id?: number | null;
  selected_beginnings_id?: number | null;
  selected_species_id?: number | null;
  selected_gender_id?: number | null;
  age?: number | null;
  family_id?: number | null;
  height_band_id?: number | null;
  height_inches?: number | null;
  build_id?: number | null;
  selected_path_id?: number | null;
  selected_tradition_id?: number | null;
  public_worship_id?: number | null;
  secret_worship_id?: number | null;
  draft_data?: Partial<DraftData>;
}

/**
 * Get default stat values for character creation.
 * All stats start at 2 during character creation.
 */
export function getDefaultStats(): Stats {
  return {
    strength: 2,
    agility: 2,
    stamina: 2,
    charm: 2,
    presence: 2,
    composure: 2,
    intellect: 2,
    wits: 2,
    stability: 2,
    luck: 2,
    perception: 2,
    willpower: 2,
  };
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

/**
 * Admin-editable explanatory text for all CG stages.
 * Key-value model — each key maps to a text string (e.g. "origin_heading").
 */
export type CGExplanations = Record<string, string>;

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

// Origin story guided flow (#2478)
export interface OriginTemplateSlot {
  id: number;
  name: string;
  prompt: string;
  example: string;
  sort_order: number;
  is_required: boolean;
}

export interface OriginTemplate {
  id: number;
  name: string;
  frame_narrative: string;
  is_active: boolean;
  sort_order: number;
  slots: OriginTemplateSlot[];
}
