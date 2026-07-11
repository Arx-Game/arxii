// ---------------------------------------------------------------------------
// Legacy scene action types (now slimmed — fetchSceneActions has been removed)
// ---------------------------------------------------------------------------

import type { PowerLedger } from '@/magic/types';

export interface TechniqueOption {
  id: number;
  name: string;
  capability_type: string;
  capability_value: number;
}

// ---------------------------------------------------------------------------
// Unified actions endpoint types — GET /api/actions/characters/<id>/available/
// ---------------------------------------------------------------------------

export interface ActionCheckType {
  id: number;
  name: string;
}

export interface ActionTemplateMinimal {
  id: number;
  name: string;
  /** Default audience routing for the action's result echo (#903). */
  default_delivery: string;
}

export interface ActionRef {
  backend: string;
  challenge_instance_id: number | null;
  approach_id: number | null;
  technique_id: number | null;
  registry_key: string | null;
  clash_id?: number | null;
  clash_action_slot?: string | null;
  /** Destination position PK — present on move_to_position registry actions (#532). */
  position_id?: number | null;
  /** Blueprint PK — present on set_the_stage registry actions (#1017). */
  blueprint_id?: number | null; // #1017
}

// ---------------------------------------------------------------------------
// Inline shape carried by PlayerAction — target spec, strain, and enhancements
// ---------------------------------------------------------------------------

export interface TargetFilters {
  in_same_scene: boolean;
  exclude_self: boolean;
  must_be_conscious: boolean;
}

export interface TargetSpec {
  kind: string;
  cardinality: string;
  filters: TargetFilters;
}

export interface StrainAvailability {
  cap: number;
  default: number;
}

export interface SoulfrayWarningData {
  stage_name: string;
  stage_description: string;
  has_death_risk: boolean;
}

export interface AvailableEnhancement {
  technique_id: number;
  technique_name: string;
  effective_cost: number;
  soulfray_warning: SoulfrayWarningData | null;
}

/**
 * A fury tier the player may commit for a combat-cast technique (#1543).
 * Mirrors the backend FuryTierOption serializer shape.
 */
export interface FuryTierOption {
  id: number;
  name: string;
  depth: number;
  control_penalty: number;
  intensity_bonus: number;
  /** 0 → never berserk; higher values increase berserk severity on overcommit. */
  berserk_severity: number;
}

/**
 * A bond/anchor eligible to cap fury commitment for a combat-cast technique (#1543).
 * Mirrors the backend AnchorOption serializer shape.
 */
export interface FuryAnchorOption {
  id: number;
  name: string;
  /** Pre-computed bond cap used for client-side tier gating. */
  provocation_cap: number;
}

export type ActionCategory = 'physical' | 'social' | 'mental';

export interface PlayerAction {
  backend: string;
  display_name: string;
  description: string;
  difficulty: string | null;
  prerequisite_met: boolean;
  prerequisite_reasons: string[];
  check_type: ActionCheckType;
  action_template: ActionTemplateMinimal | null;
  ref: ActionRef;
  target_spec: TargetSpec | null;
  enhancements: AvailableEnhancement[];
  strain: StrainAvailability | null;
  /** Physical/social/mental arena (#614). Optional on this hand-written mirror;
   *  the API always supplies it (possibly null) for technique actions. */
  action_category?: ActionCategory | null;
  /**
   * Reach constraint for target selection (#532). Values: "same" | "adjacent" | "any" | null.
   * null / "any" → no restriction; "same" → must share a position; "adjacent" → same or neighbouring.
   */
  reach?: string | null;
  /**
   * Guardian-declaration flavor for combat-cast techniques (#2207). Values:
   * "barrier" | "blink" | "redirect" | null. null → the technique carries no
   * protective reactive-trigger handler, so it can't be offered as a Guard
   * declaration's protective technique.
   */
  protective_flavor?: string | null;
  /**
   * Soulfray warning for combat-cast techniques that risk death (#1543).
   * null / absent → no death-risk warning applies.
   */
  soulfray_warning?: SoulfrayWarningData | null;
  /** Available fury commitment tiers for combat-cast techniques (#1543). */
  available_fury_tiers?: FuryTierOption[];
  /** Eligible fury anchors (bonds) that can cap fury commitment (#1543). */
  eligible_fury_anchors?: FuryAnchorOption[];
}

export interface PlayerActionsResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: PlayerAction[];
}

/** One wagered stake in a stakes-contract summary (#1770 pillar 9). */
export interface StakeSummaryEntry {
  id: number;
  player_summary: string;
  severity: number;
  severity_label: string;
}

/**
 * Beat-level stakes summary shown at commit surfaces (#1770 pillar 9).
 * What is wagered is visible; branch contents are never included.
 */
export interface StakesSummary {
  declared_risk: string;
  effective_risk: string;
  is_ready: boolean;
  stakes: StakeSummaryEntry[];
}

/** Mirrors SceneActionRequestSerializer's FLAT payload (#892 — keep in sync). */
export interface ActionRequest {
  id: number;
  /** Persona pk — the serializer emits the FK id, not a nested object. */
  initiator_persona: number;
  initiator_name: string;
  action_key: string;
  technique: number | null;
  technique_name: string | null;
  strain_commitment: number;
  /** Risk level of the encounter accepting this hostile cast would join (#777). */
  combat_risk_level?: string | null;
  /** Stakes summaries for staked beats behind the gating encounter (#1770). */
  combat_stakes?: StakesSummary[] | null;
  created_at: string;
}

export interface CheckResultData {
  outcome: string;
  success_level: number;
}

export interface ConsequenceData {
  label: string;
  outcome_tier: string;
}

export interface AppliedEffectData {
  type: string;
  condition?: string;
  duration?: string;
}

export interface TechniqueResultData {
  confirmed: boolean;
  anima_spent: number;
  soulfray_stage: string | null;
  mishap_label: string | null;
}

export interface ActionResolutionStepData {
  step_label: string;
  check_outcome: string;
  consequence_id: number | null;
}

export interface ActionResolutionData {
  current_phase: string;
  main_result: ActionResolutionStepData | null;
  gate_results: ActionResolutionStepData[];
}

export interface AnimaRecoveryData {
  recovered: number;
  soulfray_reduced: number;
  new_pool: number;
}

export interface ActionResultData {
  interaction_id: number;
  action_key: string | null;
  action_resolution: ActionResolutionData;
  technique_result: TechniqueResultData | null;
  technique_name: string | null;
  /** @deprecated Use action_resolution.main_result instead */
  check_result: CheckResultData | null;
  /** @deprecated Use technique_name instead */
  selected_consequence: ConsequenceData | null;
  applied_effects: AppliedEffectData[];
  /** Present when an anima ritual resolves; absent for all other action types. */
  anima_recovery?: AnimaRecoveryData;
}

export interface ActionRequestResponse {
  status: 'pending' | 'resolved';
  request_id?: number;
  result?: ActionResultData;
}

export interface ActionAttachmentInfo {
  actionKey: string;
  name: string;
  target?: string;
  requiresTarget: boolean;
  techniqueId?: number;
  targetPersonaId?: number;
}

export interface Place {
  id: number;
  name: string;
  description: string;
  /**
   * Whether one of the viewer's own personas is currently present at this
   * place (#2156). Served by `PlaceSerializer.viewer_is_present` — hand-typed
   * here because the generated `api.d.ts` from Task 1 doesn't carry it yet
   * (schema regen deferred to Task 8).
   */
  viewer_is_present: boolean;
}

// ---------------------------------------------------------------------------
// Standalone technique cast types
// ---------------------------------------------------------------------------

/**
 * A technique the persona can cast standalone.
 * Mirrors the CastableTechniqueSerializer shape from the backend.
 */
export interface CastableTechnique {
  id: number;
  name: string;
  anima_cost: number;
  tier: number;
  intensity: number;
  control: number;
  /** True if casting this against another PC will seed/feed a combat encounter. */
  hostile: boolean;
  /** Cardinality of target selection: "self" | "single" | "area" | "filtered_group". */
  target_type: string;
  /** Positional reach constraint: "same" | "adjacent" | "any". */
  reach: string;
  /** Target picker spec — null for SELF-targeting techniques. */
  target_spec: TargetSpec | null;
}

export interface CastPullRequestBody {
  resonance_id: number;
  tier: 1 | 2 | 3;
  thread_ids: number[];
}

export interface CastRequestBody {
  scene: number;
  initiator_persona: number;
  technique_id: number;
  target_persona?: number | null;
  /** For FILTERED_GROUP casts: the subset of personas selected by the player. */
  target_persona_ids?: number[];
  strain_commitment?: number;
  pull?: CastPullRequestBody;
}

/** Immediate-path cast result (EnhancedSceneActionResultSerializer). */
export interface CastResultPayload {
  action_key: string;
  power_ledger: PowerLedger | null;
  action_resolution: ActionResolutionData;
  technique_result: TechniqueResultData | null;
  /** Present when an anima ritual resolves; absent for all other action types. */
  anima_recovery?: AnimaRecoveryData;
}

export interface CastResponse {
  /** The created SceneActionRequest id. */
  id: number;
  status: string;
  /** Present only on the immediate path. */
  result?: CastResultPayload;
  /** Narrator OUTCOME pose id (immediate path). */
  outcome_interaction?: number;
  /**
   * ACTION interaction id whose persisted ledger backs the gated
   * action-outcome-details endpoint. For the in-response ledger data,
   * read `result.power_ledger` instead.
   */
  action_interaction?: number | null;
  /**
   * Present when this cast seeded or joined a CombatEncounter
   * (`action_views.py:601-605`). Absent for casts that don't touch combat.
   */
  encounter?: { id: number; status: string };
}

// Mirrors SceneActionTargetSerializer (#1177). Kept in sync with the backend.
export interface PendingActionTarget {
  action_target_id: number;
  action_request_id: number;
  target_persona_id: number;
  status: string;
  initiator_persona: number;
  initiator_name: string;
  scene: number;
  action_key: string;
  action_template: number | null;
  technique: number | null;
  technique_name: string | null;
  pose_text: string;
  strain_commitment: number;
  combat_risk_level?: string | null;
  /** Stakes summaries for staked beats behind the gating encounter (#1770). */
  combat_stakes?: StakesSummary[] | null;
  created_at: string;
}
