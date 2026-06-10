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
}

export interface ActionRef {
  backend: string;
  challenge_instance_id: number | null;
  approach_id: number | null;
  technique_id: number | null;
  registry_key: string | null;
  clash_id?: number | null;
  clash_action_slot?: string | null;
}

// ---------------------------------------------------------------------------
// Inline shape carried by PlayerAction — target spec, strain, and enhancements
// ---------------------------------------------------------------------------

export interface TargetFilters {
  in_same_scene: boolean;
  in_same_zone: boolean;
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
}

export interface PlayerActionsResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: PlayerAction[];
}

export interface ActionRequest {
  id: number;
  initiator_persona: { id: number; name: string };
  action_name: string;
  technique_name: string | null;
  strain_commitment: number;
  /** Risk level of the encounter accepting this hostile cast would join (#777). */
  combat_risk_level?: string | null;
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
}
