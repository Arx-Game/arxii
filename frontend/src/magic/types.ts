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
// GET /api/magic/thread-hub-summary/ — schema now correct via @extend_schema.
// Re-export generated shapes.
// ---------------------------------------------------------------------------

export type ResonanceBalance = components['schemas']['_ResonanceBalance'];
export type NearXPLockProspect = components['schemas']['_NearXPLockProspect'];
export type ThreadHubSummary = components['schemas']['ThreadHubSummary'];

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
// POST /api/magic/threads/{id}/cross_xp_lock/ — schema now correct via
// @extend_schema on the backend. Re-export generated shapes.
// ---------------------------------------------------------------------------

export type CrossXPLockRequest = components['schemas']['CrossXPLockRequest'];
export type CrossXPLockResponse = components['schemas']['CrossXPLockResponse'];

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
  /** Resonance units spent this imbue call. */
  resonance_spent?: number;
  /** Developed points accrued this call. */
  developed_points_added?: number;
  /** Thread levels advanced this call (0 if blocked before levelling). */
  levels_gained?: number;
  /** New thread level after imbuing. */
  new_level?: number;
  /** New developed_points total after imbuing. */
  new_developed_points?: number;
  /**
   * Why the imbue was blocked (or "NONE" if it succeeded fully).
   * NONE | XP_LOCK | ANCHOR_CAP | PATH_CAP | INSUFFICIENT_BUCKET
   */
  blocked_by?: string;
}

// ---------------------------------------------------------------------------
// Pull Preview
//
// POST /api/magic/thread-pull-preview/ — schema now correct via @extend_schema.
// Re-export generated shapes.
// ---------------------------------------------------------------------------

export type PullPreviewRequest = components['schemas']['ThreadPullPreviewRequestRequest'];

/** One previewed effect in the preview response. */
export type PreviewedEffect = components['schemas']['ResolvedPullEffect'];

export type PullPreviewResponse = components['schemas']['ThreadPullPreviewResponse'];

// ---------------------------------------------------------------------------
// Pull Commit
//
// POST /api/magic/thread-pull-commit/ — schema now correct via @extend_schema.
// Re-export generated shapes.
// ---------------------------------------------------------------------------

/** One resolved effect in the commit response. */
export type ResolvedPullEffect = components['schemas']['ResolvedPullEffectCommit'];

export type PullCommitRequest = components['schemas']['ThreadPullCommitRequestRequest'];

export type PullCommitResponse = components['schemas']['ThreadPullCommitResponse'];

// ---------------------------------------------------------------------------
// Teaching Offer accept
//
// POST /api/magic/teaching-offers/{id}/accept/ — schema now correct via
// @extend_schema on the backend. Re-export generated shapes.
// ---------------------------------------------------------------------------

export type AcceptTeachingOfferRequest = components['schemas']['AcceptTeachingOfferRequest'];
export type AcceptTeachingOfferResponse = components['schemas']['AcceptTeachingOfferResponse'];

// ---------------------------------------------------------------------------
// Room Brief
//
// GET /api/magic/rooms-by-property/ — schema now correct via @extend_schema.
// Re-export the generated shape.
// ---------------------------------------------------------------------------

export type RoomBrief = components['schemas']['RoomBrief'];
export type RelationshipTrack = components['schemas']['RelationshipTrack'];

// ---------------------------------------------------------------------------
// Applicable Pulls
//
// POST /api/magic/applicable-pulls/ — schema is in generated types.
// Re-export generated shapes.
// ApplicablePullsRequestRequest (note: backend naming with "Request" suffix)
// is re-exported as ApplicablePullsRequest for the frontend convention.
// ---------------------------------------------------------------------------

/** Request body for POST /api/magic/applicable-pulls/ */
export type ApplicablePullsRequest = components['schemas']['ApplicablePullsRequestRequest'];

/** One row in the applicable-pulls response: per-thread applicability status. */
export type ThreadApplicability = components['schemas']['ThreadApplicability'];
