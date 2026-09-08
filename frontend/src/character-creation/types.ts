/**
 * Character Creation types
 */

// Single definition lives with the shared guided-flow component; both CG and
// the character sheet mount (Task 6) import it from here.
export type { GlimpseTagOption } from '@/magic/components/glimpse/glimpseTypes';

// Single definition lives in the magic module (#2898) — every technique
// surface imports the same shape rather than re-declaring it.
import type { TechniqueEffectSummary } from '@/magic/types';
export type { TechniqueEffectSummary } from '@/magic/types';

// Reused for FamilyTemplate below: the house-claim template shape
// (aspect_definitions/features) already generated from the backend schema,
// extended rather than duplicated (#3648).
import type { components } from '@/generated/api';

export interface StartingArea {
  id: number;
  name: string;
  description: string;
  crest_image: string | null;
  is_accessible: boolean;
  realm_theme: string;
}

/** The world fact behind a heritage's CG age ceiling (#3663). */
export interface BeginningsHeritage {
  name: string;
  /** IC year the first of this heritage were born; null when the heritage has no anchor. */
  first_appeared_ic_year: number | null;
}

export interface Beginnings {
  id: number;
  name: string;
  description: string;
  art_image: string | null;
  allowed_species_ids: number[];
  grants_species_languages: boolean;
  cg_point_cost: number;
  is_accessible: boolean;
  codex_entry_ids: number[];
  heritage: BeginningsHeritage | null;
}

/**
 * A holder's opinion about another subject, surfaced during CG picks (#3281).
 * From GET /api/character-creation/beginnings/{id}/perspectives/ and
 * GET /api/character-creation/traditions/{id}/perspectives/.
 */
export interface PerspectiveEntry {
  entry_id: number;
  name: string;
  summary: string;
  lore_content: string;
  subject_name: string;
}

export interface Species {
  id: number;
  name: string;
  description: string;
  parent?: number | null;
  parent_name?: string | null;
  stat_bonuses: Record<string, number>;
  codex_entry_id: number | null;
  eternal_youth: boolean;
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

/** Facts a character inherits from their family's Family Template (#3648). */
export interface InheritedFacts {
  aspects: { definition: string; option: string; description: string }[];
  features: { name: string; slug: string; description: string }[];
  liege_name: string;
}

export interface Family {
  id: number;
  name: string;
  // #3617: authored kind row (was a 'commoner' | 'noble' | 'crime' code).
  kind: { id: number; name: string; styles_as_house: boolean };
  influence: number;
  description: string;
  origin_realm?: number;
  // #3261 — resolved nobiliary particles ('' when the family has none).
  born_particle: string;
  taken_in_particle: string;
  /** Aspects/features/liege inherited from the family's Family Template (#3648). */
  inherited: InheritedFacts;
}

/**
 * A Family Template the name path builds from (#3648): the same shape a
 * house-claim template uses (aspect_definitions, features), extended with
 * the fields the Upbringing name path needs rather than duplicated.
 */
export type FamilyTemplate = components['schemas']['HouseTemplateOption'] & {
  org_type: number;
  served_house_choices: { id: number; name: string }[];
};

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

/** An opening on a staff family, priced for this draft (#3648). */
export interface Vacancy {
  id: number;
  name: string;
  description: string;
  basis: 'kin' | 'retainer';
  importance: number;
  presumed_importance: number;
  cost: number;
  rank_name: string;
  count_remaining: number | null;
  organization: {
    id: number;
    name: string;
    family: { id: number; name: string; influence: number } | null;
  };
  kin_pool: KinSlotPool | null;
  kin_node: KinSlot | null;
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
 * Paths are the narrative-focused class system for Arx.
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
  /** Staff-authored copy shown on this band's option (#3675 Task 15 fix round 1),
   * e.g. what opens a band players cannot normally take. Empty when unauthored. */
  cg_hint: string;
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
  trait_type: 'color' | 'style' | 'feature';
}

export interface FormTraitWithOptions {
  trait: FormTrait;
  is_required: boolean;
  options: FormTraitOption[];
}

/** Cross-line options unlocked by a cross-species parent (#2815). */
export interface InheritedTraitGroup {
  trait: FormTrait;
  options: FormTraitOption[];
  source: string;
}

export interface FormOptionsResponse {
  traits: FormTraitWithOptions[];
  inherited: InheritedTraitGroup[];
}

export enum Stage {
  ORIGIN = 1,
  HERITAGE = 2,
  LINEAGE = 3,
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
  birthday_month: number | null;
  birthday_day: number | null;
  family: Family | null;
  /** The Upbringing chosen for the Lineage stage and the family path it took (#3617). */
  selected_origin_template: OriginTemplate | null;
  family_path: FamilyPath | '';
  claimed_kin_slot: number | null;
  claimed_kin_pool: number | null;
  /** The Vacancy chosen on the name path, when the Upbringing offers one (#3648). */
  selected_vacancy: number | null;
  /** The house the chosen Vacancy's holder serves, when the vacancy allows a choice (#3648). */
  served_house: number | null;
  defer_parents: boolean;
  /** Species id of the invented non-dominant parent when cross-species (#2815). */
  second_parent_species: number | null;
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
  /** The age range CG accepts for this draft; the server composes every cap (#3663). */
  age_min: number;
  age_max: number;
  /** Distinctions the draft's visible, picked Upbringing answers grant (#3660). */
  bundled_distinctions: BundledDistinction[];
  /**
   * OWN_FAMILY/SERVED_HOUSE GROUP questions' resolved org, keyed by slot id as a
   * string, or `null` when that source has nothing to resolve to yet (#3660 ruling
   * L). The frontend cannot derive these itself (no house org id for a claimed
   * family, no served-house lookup without the offering Family Template), so the
   * server hands back what it resolved.
   */
  derived_anchors: Record<string, DerivedAnchor | null>;
  /** Who the draft may name as its enemy (#3621): Lineage groups and persons, Beginning offers. */
  enemy_offers: EnemyOffer[];
  /** Both price scales, reach or power tier -> degree -> CG points awarded (#3621). */
  enemy_price_tables: Record<'group' | 'person', Record<string, Record<string, number>>>;
  /** Degree value -> the Distinction that degree grants (#3621), so the row can say so. */
  enemy_degree_grants: Record<string, string>;
  /** The authored reason list (#3709); the leaf filters it by the enemy's kind. */
  enemy_reasons: EnemyReason[];
  /** Which Introductions this draft is offered; the First Journal needs an Arx start (#3621). */
  introductions_offered: { first_journal: boolean };
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
 * One standard schooling stance under a `living_masters` tradition (#3675).
 * Embedded on `Tradition.schooling`.
 */
export interface SchoolingLineRow {
  schooling_line_id: number;
  rank: number;
  name: string;
  player_line: string;
  price: number;
  techniques: number;
  grants_distinction_id: number | null;
  offer_id: number | null;
}

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
  /** Whether this tradition still has living teachers (#3675). */
  state: 'self_taught' | 'teachers_gone' | 'living_masters';
  state_line: string;
  own_wording: string;
  refund: number;
  schooling: SchoolingLineRow[];
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
 * Technique row for the CG technique-options list (pool ∪ signature ∪ species gift).
 * From GET /api/character-creation/technique-options/?draft_id=<id>&gift_id=<id>
 */
export interface CGTechniqueOption {
  id: number;
  name: string;
  description: string;
  category: 'attack' | 'defense' | 'buff' | 'debuff' | 'utility';
  codex_entry_id: number | null;
  is_tradition_technique: boolean;
  is_species_technique: boolean;
  /**
   * The shared effect block (#2898) — cost, reach, targeting, hostility, and
   * the plain-words summary line. CG is where a technique pick is least
   * reversible, so this is the surface that most needs it.
   */
  effect_summary: TechniqueEffectSummary;
}

// =============================================================================
// NEW Magic System Types (Build-Your-Own)
// =============================================================================

/**
 * Technique style — how a practitioner works magic. A property of the caster's
 * Path (#2700), not of the technique.
 * From /api/magic/styles/
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

export type GoalHorizon = 'short_term' | 'long_term';

export interface DraftGoal {
  domain_id: number;
  notes: string;
  points: number;
  /** Short term or long term (#3621); numbered within the horizon in list order. */
  horizon: GoalHorizon;
}

/** The draft's enemy pick (#3621): a person or a group, at a degree. */
export interface DraftEnemy {
  kind: 'person' | 'group';
  organization_id: number | null;
  /** The person's name, or a free-written group's name; blank for an offered group. */
  name: string;
  /** A person's power on the ladder; blank for a group. */
  power_tier: string;
  degree: string;
  why: string;
  public_line: string;
  /** The authored reason picked (#3709), or null for none. */
  reason_id: number | null;
}

/** The Introductions' answers (#3621): three per journal, one rumor per line for the Whispers. */
export interface DraftIntroductions {
  first_journal: string[];
  application: string[];
  whispers: string;
}

/** One person or group the draft may name as its enemy (#3621, `enemy_offers`). */
export interface EnemyOffer {
  kind: 'person' | 'group';
  organization_id: number | null;
  name: string;
  reach: string;
  power_tier: string;
  why: string;
  source: 'lineage' | 'beginning';
  /** The reason a Beginning's offer arrives with already set (#3709), or null. */
  reason_id: number | null;
}

export interface DraftData {
  first_name?: string;
  description?: string;
  background?: string;
  // The Actor's Sheet (#3621): the three answers, the enemy pick, the Introductions
  never_do?: string;
  protect?: string;
  fear?: string;
  enemy?: DraftEnemy | null;
  introductions?: DraftIntroductions;
  // Origin story guided flow (#2478); Upbringing prompt answers (#3617)
  origin_slots?: Record<string, string>;
  // Upbringing pick-list prompt answers: slot id -> choice id or null (#3617)
  origin_choices?: Record<string, number | null>;
  // GROUP question answers: slot id -> organization id or null (#3660). Never
  // set for an own_family/served_house question; the server resolves those.
  origin_anchors?: Record<string, number | null>;
  // PERSON question answers: slot id -> the named person's name (#3660)
  origin_figures?: Record<string, string>;
  // The name given to a newly founded family on the 'named' family path (#3617)
  new_family_name?: string;
  concept?: string;
  quote?: string;
  stats?: Stats;
  path_skills_complete?: boolean;
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
  // Magic fields - Gift resonance (anchors the latent GIFT thread at CG finalization, #1620)
  selected_gift_resonance_id?: number | null;
  magic_complete?: boolean;
  // Tarot card selection for familyless characters
  tarot_card_name?: string;
  tarot_reversed?: boolean;
  // Invented parents (#2815) — names + genders; species rides
  // CharacterDraft.second_parent_species
  line_parent_name?: string;
  other_parent_name?: string;
  line_parent_gender_id?: number | null;
  other_parent_gender_id?: number | null;
  // Goals for Final Touches stage
  goals?: DraftGoal[];
  // The Family Template picked on the name path, when the Upbringing offers
  // more than one (#3648); resolveFamilyTemplate() resolves the effective one.
  // null clears the pick (the backend treats null as unset; undefined would
  // be dropped by the JSON encoder and leave the prior pick untouched).
  family_template_id?: number | null;
  // Aspect picks for the chosen Family Template: definition id -> option ids (#3648).
  family_aspect_picks?: Record<string, number[]>;
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
  birthday_month?: number | null;
  birthday_day?: number | null;
  family_id?: number | null;
  selected_origin_template_id?: number | null;
  family_path?: FamilyPath | '';
  height_band_id?: number | null;
  height_inches?: number | null;
  build_id?: number | null;
  selected_path_id?: number | null;
  selected_tradition_id?: number | null;
  public_worship_id?: number | null;
  secret_worship_id?: number | null;
  second_parent_species_id?: number | null;
  selected_vacancy_id?: number | null;
  served_house_id?: number | null;
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
  never_do: string;
  protect: string;
  fear: string;
  background: string;
  species: string | null;
  area: string | null;
  beginnings: string | null;
  family: string | null;
  gender: string | null;
  age: number | null;
  stage_completion: Record<number, boolean>;
}

// Origin story guided flow (#2478); extended into the Upbringing model (#3617)

/** A `DistinctionOffer` embedded on an Upbringing answer row (#3675). */
export interface AnswerOffer {
  offer_id: number;
  distinction_id: number;
  name: string;
  player_line: string;
  arrives_as: 'choice' | 'bundled';
  cost_per_rank: number;
  max_rank: number;
}

/** One priced answer on a pick-list Upbringing prompt. */
export interface OriginTemplateSlotChoice {
  id: number;
  name: string;
  description: string;
  cg_point_cost: number;
  cost_per_influence: number;
  /** Minimum trust to see this answer; staff always see it (#3660). */
  trust_required: number;
  offers: AnswerOffer[];
  sort_order: number;
}

/** The family path a slot prompt is scoped to, or 'any' for every path. */
export type FamilyPath = 'claimed' | 'named' | 'none';

/** What kind of thing an Upbringing prompt asks for (#3660). */
export type QuestionKind = 'text' | 'pick' | 'group' | 'person';

/** Which groups a 'group' question offers, or '' for a non-group question (#3660). */
export type AnchorSource = '' | 'pool' | 'listed' | 'same_as' | 'served_house' | 'own_family';

/**
 * An OWN_FAMILY/SERVED_HOUSE GROUP question's resolved org (#3660 ruling L).
 * Mirrors the generated `DerivedAnchor` schema - no `gloss`, unlike `OriginGroup`,
 * since this backs a fact card, not a picker.
 */
export interface DerivedAnchor {
  id: number;
  name: string;
  influence: number | null;
}

/** One group a GROUP question offers, for the frontend picker (#3660). */
export interface OriginGroup {
  id: number;
  name: string;
  gloss: string;
  influence: number | null;
}

export interface OriginTemplateSlot {
  id: number;
  name: string;
  prompt: string;
  example: string;
  sort_order: number;
  is_required: boolean;
  applies_to: 'any' | FamilyPath;
  allows_text: boolean;
  kind: QuestionKind;
  /** What the tie was; a tag shown on the page and the sheet (#3660). */
  connection_kind: string;
  /** When the tie was formed; a tag (#3660). */
  life_stage: string;
  /** Which groups a 'group' question offers (#3660). */
  anchor_source: AnchorSource;
  /** GROUP with SAME_AS: the earlier group question whose answer is this anchor.
   *  PERSON: the group question this person belongs to (#3660). */
  same_anchor_as: number | null;
  /** Shown only once this earlier question is answered (#3660). */
  follow_up_to: number | null;
  /** Choice ids on `follow_up_to` that reveal this slot; `[]` means any answer. */
  shown_for_choice_ids: number[];
  /** Groups a POOL/LISTED question offers; `[]` for every other source (#3660). */
  groups: OriginGroup[];
  choices: OriginTemplateSlotChoice[];
}

/** A tag label for `OriginTemplateSlot.connection_kind` (#3660). */
export const CONNECTION_KIND_LABELS: Record<string, string> = {
  raised_by: 'Raised by',
  taught_by: 'Taught by',
  served: 'Served',
  sailed_with: 'Sailed with',
  owes: 'Owes',
  sworn_to: 'Sworn to',
  hunted_by: 'Hunted by',
};

/** A tag label for `OriginTemplateSlot.life_stage` (#3660). */
export const LIFE_STAGE_LABELS: Record<string, string> = {
  childhood: 'Childhood',
  youth: 'Youth',
  at_the_glimpse: 'At the Glimpse',
  since_the_glimpse: 'Since the Glimpse',
};

/** A Distinction bundled at no extra cost by a picked Upbringing answer (#3660). */
export interface BundledDistinction {
  distinction_id: number;
  name: string;
  cost_per_rank: number;
  secret_by_default: boolean;
  slot_id: number;
  slot_name: string;
  choice_id: number;
  choice_name: string;
  organization_id: number | null;
  organization_name: string;
}

/** An "Upbringing" in CG copy: the authored content row chosen in the Lineage step. */
export interface OriginTemplate {
  id: number;
  name: string;
  frame_narrative: string;
  is_active: boolean;
  sort_order: number;
  cg_point_cost: number;
  trust_required: number;
  allows_claim_family: boolean;
  allows_name_family: boolean;
  allows_no_family: boolean;
  claimable_kind_ids: number[];
  /** Family Templates offered on the name path (#3648; replaces named_family_kind). */
  family_templates: FamilyTemplate[];
  slots: OriginTemplateSlot[];
}

/** The family paths this Upbringing allows, in claim/name/none order. */
export function allowedFamilyPaths(t: OriginTemplate): FamilyPath[] {
  const paths: FamilyPath[] = [];
  if (t.allows_claim_family) paths.push('claimed');
  if (t.allows_name_family) paths.push('named');
  if (t.allows_no_family) paths.push('none');
  return paths;
}

/**
 * The family path in effect for the draft's chosen Upbringing: the single
 * allowed path when there is only one, the draft's stored pick when it is
 * still one of the allowed paths, or '' when nothing is resolved yet.
 */
export function resolveFamilyPath(draft: CharacterDraft): FamilyPath | '' {
  const t = draft.selected_origin_template;
  if (!t) return '';
  const allowed = allowedFamilyPaths(t);
  if (allowed.length === 1) return allowed[0];
  return allowed.includes(draft.family_path as FamilyPath) ? (draft.family_path as FamilyPath) : '';
}

/** The Family Template in effect on the name path: the only one, else the stored pick. */
export function resolveFamilyTemplate(draft: CharacterDraft): FamilyTemplate | null {
  const offered = draft.selected_origin_template?.family_templates ?? [];
  if (offered.length === 1) return offered[0];
  const chosen = draft.draft_data.family_template_id;
  return offered.find((t) => t.id === chosen) ?? null;
}

/** A pick-list choice's CG point cost, scaled by the claimed family's influence. */
export function choiceCost(choice: OriginTemplateSlotChoice, influence: number): number {
  return choice.cg_point_cost + choice.cost_per_influence * influence;
}

/**
 * Whether the draft has answered `slot` in the way its kind needs (#3660).
 * Mirrors `world.character_creation.questionnaire.is_answered`.
 */
/** Whether a GROUP question has an anchor to answer with, by anchor source (#3660). */
function hasGroupAnchor(slot: OriginTemplateSlot, draft: CharacterDraft): boolean {
  if (slot.anchor_source === 'own_family' || slot.anchor_source === 'served_house') {
    // The server is the only side that can resolve these (ruling L): a claimable
    // family with no house org, or no served house picked yet, must read as
    // unanswered here too, not just at validation - `draft.family`/`served_house`
    // being set is not the same thing as the org resolving.
    return draft.derived_anchors[String(slot.id)] != null;
  }
  return (draft.draft_data.origin_anchors?.[String(slot.id)] ?? null) != null;
}

export function isAnswered(slot: OriginTemplateSlot, draft: CharacterDraft): boolean {
  const picked = draft.draft_data.origin_choices?.[String(slot.id)] ?? null;
  const validPick = picked != null && slot.choices.some((c) => c.id === picked);
  const text = Boolean((draft.draft_data.origin_slots?.[String(slot.id)] ?? '').trim());
  if (slot.kind === 'text') return text;
  if (slot.kind === 'pick') return validPick || (slot.allows_text && text);
  if (slot.kind === 'person') {
    return Boolean((draft.draft_data.origin_figures?.[String(slot.id)] ?? '').trim());
  }
  // GROUP: an anchor, plus a stance when the question offers any.
  const hasAnchor = hasGroupAnchor(slot, draft);
  if (slot.choices.length === 0) return hasAnchor;
  return hasAnchor && validPick;
}

/**
 * Ids of the questions shown to this draft, evaluated in sort order (#3660).
 * Mirrors `world.character_creation.questionnaire.is_shown`/`visible_slot_ids`.
 */
export function shownSlotIds(
  template: OriginTemplate,
  draft: CharacterDraft,
  path: FamilyPath | ''
): Set<number> {
  const slots = [...template.slots].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  const slotsById = new Map(slots.map((s) => [s.id, s]));
  const picks = draft.draft_data.origin_choices ?? {};
  const shown = new Set<number>();
  for (const slot of slots) {
    if (slot.applies_to !== 'any' && slot.applies_to !== path) continue;
    if (slot.follow_up_to == null) {
      shown.add(slot.id);
      continue;
    }
    const target = slotsById.get(slot.follow_up_to);
    if (!target || !shown.has(target.id) || !isAnswered(target, draft)) continue;
    if (slot.shown_for_choice_ids.length === 0) {
      shown.add(slot.id);
      continue;
    }
    const targetPick = picks[String(target.id)];
    if (targetPick != null && slot.shown_for_choice_ids.includes(targetPick)) {
      shown.add(slot.id);
    }
  }
  return shown;
}

/**
 * The groups a GROUP question offers this draft, for the picker (#3660).
 * POOL/LISTED come straight from the slot's own `groups`; SAME_AS looks up the
 * earlier question's `groups` by its stored anchor id; SERVED_HOUSE/OWN_FAMILY
 * resolve from draft state the server also derives at validation/finalize time.
 */
export function groupsFor(
  slot: OriginTemplateSlot,
  template: OriginTemplate,
  draft: CharacterDraft
): OriginGroup[] {
  switch (slot.anchor_source) {
    case 'pool':
    case 'listed':
      return slot.groups;
    case 'same_as': {
      const target = template.slots.find((s) => s.id === slot.same_anchor_as);
      if (!target) return [];
      const anchorId = draft.draft_data.origin_anchors?.[String(target.id)] ?? null;
      if (anchorId == null) return [];
      const found = groupsFor(target, template, draft).find((g) => g.id === anchorId);
      return found ? [found] : [];
    }
    case 'served_house':
    case 'own_family': {
      // Neither source has a stored answer to look up client-side: the server
      // resolves the real org (a claimed family's house, or the served house
      // pick) and hands it back on the draft (#3660 ruling L). A DerivedAnchor
      // carries no gloss (it backs a fact card, not a picker), so it maps into
      // the OriginGroup shape with an empty one.
      const anchor = draft.derived_anchors[String(slot.id)] ?? null;
      return anchor ? [{ ...anchor, gloss: '' }] : [];
    }
    default:
      return [];
  }
}

/**
 * The single group currently in effect for a GROUP question: the only offered
 * group (SAME_AS/SERVED_HOUSE/OWN_FAMILY, or a single-item POOL/LISTED list),
 * else the player's stored pick among several offered groups (#3660).
 */
export function chosenGroupForSlot(
  slot: OriginTemplateSlot,
  template: OriginTemplate,
  draft: CharacterDraft
): OriginGroup | null {
  const groups = groupsFor(slot, template, draft);
  if (groups.length === 1) return groups[0];
  const anchorId = draft.draft_data.origin_anchors?.[String(slot.id)] ?? null;
  return groups.find((g) => g.id === anchorId) ?? null;
}

/**
 * Influence that multiplies `cost_per_influence` for one question's answer
 * (#3660). A GROUP question prices off its chosen group's own influence;
 * every other question keeps pricing off the claimed family's influence.
 */
export function questionInfluence(
  slot: OriginTemplateSlot,
  group: OriginGroup | null,
  draft: CharacterDraft,
  path: FamilyPath | ''
): number {
  if (slot.kind === 'group') return group?.influence ?? 0;
  if (path === 'claimed' && draft.family) return draft.family.influence;
  return 0;
}

// =============================================================================
// Distinctions are offered by CG chapter (#3675), not a standalone stage:
// each chapter (Path/Tradition, Glimpse, Lineage, Appearance, the
// Actor's Sheet) surfaces the offers it opens via
// GET /api/character-creation/drafts/{id}/offers/?chapter=<OfferChapter>.
// =============================================================================

/** Which CG chapter's `GET .../offers/?chapter=` is being requested (#3675). */
export type OfferChapter =
  | 'tradition_step'
  | 'glimpse'
  | 'lineage'
  | 'appearance'
  | 'actors_sheet'
  | 'enemy';

/** A distinction offer visible to the draft in the requested chapter (#3675). */
export type VisibleOffer = components['schemas']['VisibleOffer'];

/** One authored reason an enemy wants the character to fail (#3709). */
export type EnemyReason = components['schemas']['EnemyReason'];

/** A distinction the draft can no longer take, and why (#3675). */
export type ClosedDistinction = components['schemas']['ClosedDistinction'];

/** The `offers`/`closed` payload `GET .../offers/?chapter=` returns (#3675). */
export type OffersResponse = components['schemas']['OffersResponse'];
