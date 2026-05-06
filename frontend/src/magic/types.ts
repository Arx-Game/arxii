/**
 * Types for the magic module.
 *
 * Re-exports generated schemas for Thread, CharacterResonance, SineatingPendingOffer,
 * and PendingStageAdvanceOffer. Local types cover request bodies and response shapes
 * that the generated schema left as `content?: never` (e.g. soul-tether detail,
 * sineating offer response, rescue outcome).
 */

import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Re-exports from generated schema
// ---------------------------------------------------------------------------

export type Thread = components['schemas']['Thread'];
export type PaginatedThreadList = components['schemas']['PaginatedThreadList'];
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
