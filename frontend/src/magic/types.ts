/**
 * Types for the magic module.
 *
 * Re-exports generated schemas for Thread, CharacterResonance, SineatingPendingOffer,
 * PendingStageAdvanceOffer, Ritual, ThreadWeavingTeachingOffer, and related list types.
 * Local types cover request bodies and response shapes that the generated schema left
 * as `content?: never` (e.g. soul-tether detail, sineating offer response, rescue
 * outcome, thread hub summary, pull preview/commit).
 */

import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Re-exports from generated schema
// ---------------------------------------------------------------------------

export type Thread = components['schemas']['Thread'];
export type PaginatedThreadList = components['schemas']['PaginatedThreadList'];
export type Ritual = components['schemas']['Ritual'];
export type ThreadWeavingTeachingOffer = components['schemas']['ThreadWeavingTeachingOffer'];
export type PaginatedTeachingOfferList =
  components['schemas']['PaginatedThreadWeavingTeachingOfferList'];

// TargetKind — re-export from generated enum
export type TargetKind = components['schemas']['TargetKindEnum'];
export type CharacterResonance = components['schemas']['CharacterResonance'];
export type SineatingPendingOffer = components['schemas']['SineatingPendingOffer'];
export type PaginatedSineatingPendingOfferList =
  components['schemas']['PaginatedSineatingPendingOfferList'];
export type PendingStageAdvanceOffer = components['schemas']['PendingStageAdvanceOffer'];
export type PaginatedPendingStageAdvanceOfferList =
  components['schemas']['PaginatedPendingStageAdvanceOfferList'];

// ---------------------------------------------------------------------------
// Soul Tether detail response
//
// The generated schema for GET /api/magic/soul-tether/{relationship_id}/
// has `content?: never` — drf-spectacular does not know the response shape
// because SoulTetherDetailSerializer derives from serializers.Serializer, not
// a model. We declare the shape manually from SoulTetherDetailSerializer.
// ---------------------------------------------------------------------------

export interface SoulTetherDetail {
  relationship_id: number;
  is_soul_tether: boolean;
  soul_tether_role: string; // 'ABYSSAL' | 'CELESTIAL' from SoulTetherRole choices
  sinner_sheet_id: number | null;
  sineater_sheet_id: number | null;
  hollow_current: number;
  hollow_max: number;
  sineater_lifetime_helped: number;
  sinner_corruption_stage: number;
  sineater_strain_stage: number;
}

// ---------------------------------------------------------------------------
// Dissolve request body
// ---------------------------------------------------------------------------

export interface DissolveRequest {
  actor_sheet_id: number;
  relationship_id: number;
}

// ---------------------------------------------------------------------------
// Sineating request body + offer response
//
// POST /api/magic/soul-tether/sineating/request/ accepts SineatingRequestSerializer.
// It returns a SineatingOffer which drf-spectacular marks as no body (the view uses
// a plain Serializer). We type the response from SineatingOfferSerializer.
// ---------------------------------------------------------------------------

export interface SineatingRequest {
  actor_sheet_id: number;
  sineater_sheet_id: number;
  resonance_id: number;
  max_units: number;
  scene_id: number;
}

export interface SineatingOffer {
  sinner_sheet_id: number;
  sineater_sheet_id: number;
  resonance_id: number;
  max_units_offered: number;
  anima_cost_per_unit: number;
  fatigue_cost_per_unit: number;
  current_hollow: number;
  hollow_max: number;
  sineater_current_strain_stage: number;
}

// ---------------------------------------------------------------------------
// Sineating respond body + result response
//
// POST /api/magic/soul-tether/sineating/respond/ accepts SineatingRespondSerializer.
// Response shape from SineatingResultSerializer.
// ---------------------------------------------------------------------------

export interface SineatingRespondRequest {
  sinner_sheet_id: number;
  sineater_sheet_id: number;
  units_accepted: number; // 0 = decline
}

export interface SineatingResult {
  units_accepted: number;
  declined: boolean;
  new_hollow_current: number;
  new_lifetime_helped: number;
  audit_row_id: number;
}

// ---------------------------------------------------------------------------
// Rescue request + outcome
//
// POST /api/magic/soul-tether/rescue/ accepts SoulTetherRescueSerializer.
// Response shape from RescueOutcomeSerializer.
// ---------------------------------------------------------------------------

export interface RescueRequest {
  actor_sheet_id: number;
  sinner_sheet_id: number;
  resonance_id: number;
  scene_id: number;
}

export interface RescueOutcome {
  severity_reduced: number;
  sinner_stage_at_start: number;
  sinner_stage_at_end: number;
  sineater_strain_taken: number;
  protagonism_lock_lifted: boolean;
  audit_row_id: number;
}

// ---------------------------------------------------------------------------
// Stage-advance respond request + result
//
// POST /api/magic/soul-tether/stage-advance/respond/ accepts StageAdvanceRespondSerializer.
// Response shape from StageAdvanceBonusResultSerializer.
// ---------------------------------------------------------------------------

export interface StageAdvanceRespondRequest {
  sinner_sheet_id: number;
  sineater_sheet_id: number;
  units_committed: number; // 0 = decline
}

export interface StageAdvanceBonusResult {
  offer_id: string;
  units_committed: number;
  hollow_drained: number;
  strain_severity_added: number;
  declined: boolean;
}

// ---------------------------------------------------------------------------
// Tether bond — returned by getMyTetherBonds / useMyTetherBonds
//
// Derived from CharacterRelationshipList rows where is_soul_tether=true.
// One entry per relationship; source vs target is normalised so bonded_*
// always refers to the other party.
// ---------------------------------------------------------------------------

export interface TetherBond {
  relationship_id: number;
  bonded_character_sheet_id: number;
  bonded_character_name: string;
  soul_tether_role: string; // 'ABYSSAL' | 'SINEATER'
}

// ---------------------------------------------------------------------------
// Thread Hub Summary
//
// GET /api/magic/thread-hub-summary/ returns this shape.
// The generated schema has content?: never for this operation.
// ---------------------------------------------------------------------------

export interface ResonanceBalance {
  resonance_id: number;
  balance: number;
  lifetime_earned: number;
  flavor_text: string;
}

export interface NearXPLockProspect {
  thread_id: number;
  boundary_level: number;
  xp_cost: number;
  dev_points_to_boundary: number;
}

export interface ThreadHubSummary {
  balances: ResonanceBalance[];
  ready_thread_ids: number[];
  near_xp_lock_thread_ids: NearXPLockProspect[];
  blocked_thread_ids: number[];
  weaving_eligibility: Record<TargetKind, boolean>;
}

// ---------------------------------------------------------------------------
// Weave Thread (POST /api/magic/threads/)
//
// WeaveThreadRequest maps to the generated ThreadRequest schema.
// PatchThreadRequest maps to PatchedThreadRequest.
// ---------------------------------------------------------------------------

export interface WeaveThreadRequest {
  resonance: number;
  target_kind: TargetKind;
  target_id: number;
  character_sheet_id: number;
  name?: string;
  description?: string;
}

export interface PatchThreadRequest {
  name?: string;
  description?: string;
}

// ---------------------------------------------------------------------------
// Cross XP-lock
//
// POST /api/magic/threads/{id}/cross_xp_lock/ — the generated schema uses
// ThreadRequest as the request body and returns Thread. We model the
// request body with just the fields the action needs.
// ---------------------------------------------------------------------------

export interface CrossXPLockRequest {
  character_sheet_id: number;
  resonance: number;
}

export type CrossXPLockResponse = Thread;

// ---------------------------------------------------------------------------
// Imbue Thread
//
// Imbuing is performed via POST /api/magic/rituals/perform/ with a
// service ritual whose service_function_path = spend_resonance_for_imbuing.
// ImbueRequest carries the kwargs; the caller must resolve ritual_id first.
// ---------------------------------------------------------------------------

export interface ImbueRequest {
  ritual_id: number;
  character_sheet_id: number;
  kwargs: {
    thread_id: number;
    amount: number;
  };
}

export interface ImbueResponse {
  success: boolean;
  message?: string;
}

// ---------------------------------------------------------------------------
// Pull Preview
//
// POST /api/magic/thread-pull-preview/ — content?: never in generated schema.
// ---------------------------------------------------------------------------

export interface PullPreviewRequest {
  character_sheet_id: number;
  resonance_id: number;
  tier: 1 | 2 | 3;
  thread_ids: number[];
}

export interface PreviewedEffect {
  kind: string;
  authored_value: number | null;
  level_multiplier: number;
  scaled_value: number | null;
  vital_target: string | null;
  source_thread_id: number;
  source_thread_level: number;
  source_tier: number;
  granted_capability_id: number | null;
  narrative_snippet: string;
  inactive: boolean;
  inactive_reason: string | null;
}

export interface PullPreviewResponse {
  resonance_cost: number;
  anima_cost: number;
  previewed_effects: PreviewedEffect[];
}

// ---------------------------------------------------------------------------
// Pull Commit
//
// POST /api/magic/thread-pull-commit/ — content?: never in generated schema.
// ---------------------------------------------------------------------------

export interface ResolvedPullEffect {
  kind: string;
  authored_value: number | null;
  level_multiplier: number;
  scaled_value: number | null;
  vital_target: string | null;
  source_thread_id: number;
  source_thread_level: number;
  source_tier: number;
  granted_capability_id: number | null;
  narrative_snippet: string;
  inactive: boolean;
  inactive_reason: string | null;
}

export interface PullCommitRequest {
  character_sheet_id: number;
  resonance_id: number;
  tier: 1 | 2 | 3;
  thread_ids: number[];
  action_context?: {
    combat_encounter_id?: number | null;
    combat_participant_id?: number | null;
    involved_trait_ids?: number[];
    involved_technique_ids?: number[];
    involved_object_ids?: number[];
  };
}

export interface PullCommitResponse {
  resonance_spent: number;
  anima_spent: number;
  resolved_effects: ResolvedPullEffect[];
}

// ---------------------------------------------------------------------------
// Teaching Offer accept
//
// POST /api/magic/teaching-offers/{id}/accept/ — the generated schema
// shows no request body; response is ThreadWeavingTeachingOffer.
// ---------------------------------------------------------------------------

export interface AcceptTeachingOfferRequest {
  learner_sheet_id?: number;
}

export type AcceptTeachingOfferResponse = ThreadWeavingTeachingOffer;

// ---------------------------------------------------------------------------
// Room Brief
//
// GET /api/magic/rooms-by-property/ — content?: never in generated schema.
// A minimal room shape for the thread-weaving room picker.
// ---------------------------------------------------------------------------

export interface RoomBrief {
  id: number;
  name: string;
  location_name: string | null;
  property_ids: number[];
}
