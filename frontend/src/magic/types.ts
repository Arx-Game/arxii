/**
 * Types for the magic module.
 *
 * Re-exports generated schemas for Thread, CharacterResonance, SineatingPendingOffer,
 * PendingStageAdvanceOffer, Ritual, ThreadWeavingTeachingOffer, and related list types.
 * The soul-tether / Audere / Audere Majora respond + detail endpoints are now annotated
 * with `@extend_schema` (#920), so their request/response shapes are re-exported from the
 * generated schema too. The few remaining local types cover shapes with no 1:1 serializer
 * (e.g. TetherBond, ImbueRequest/Response, the alteration-resolve union, technique design).
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
// Soul Tether respond/detail endpoints — generated via @extend_schema (#920)
//
// These endpoints use plain `serializers.Serializer` classes. With
// `@extend_schema` on each view, drf-spectacular now emits proper request and
// response components, so we re-export the generated shapes instead of
// hand-rolling them (which could drift from the backend serializers).
// ---------------------------------------------------------------------------

export type SoulTetherDetail = components['schemas']['SoulTetherDetail'];
export type DissolveRequest = components['schemas']['DissolveRequest'];

// SineatingRequestSerializer is a request body, so the generated component
// carries drf-spectacular's "Request" suffix (→ SineatingRequestRequest).
export type SineatingRequest = components['schemas']['SineatingRequestRequest'];
export type SineatingOffer = components['schemas']['SineatingOffer'];

export type SineatingRespondRequest = components['schemas']['SineatingRespondRequest'];
export type SineatingResult = components['schemas']['SineatingResult'];

// RescueRequest maps to the generated SoulTetherRescueRequest component.
export type RescueRequest = components['schemas']['SoulTetherRescueRequest'];
export type RescueOutcome = components['schemas']['RescueOutcome'];

export type StageAdvanceRespondRequest = components['schemas']['StageAdvanceRespondRequest'];
export type StageAdvanceBonusResult = components['schemas']['StageAdvanceBonusResult'];

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
// Teaching Offer accept
//
// POST /api/magic/teaching-offers/{id}/accept/ — schema now correct via
// @extend_schema on the backend. Re-export generated shapes.
// ---------------------------------------------------------------------------

export type AcceptTeachingOfferRequest = components['schemas']['AcceptTeachingOfferRequest'];
export type AcceptTeachingOfferResponse = components['schemas']['AcceptTeachingOfferResponse'];
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

// ---------------------------------------------------------------------------
// Technique Builder — price/author request + cost breakdown response
//
// POST /api/magic/techniques/price/ and /api/magic/techniques/author/
// The generated schema uses TechniqueRequest for the request body and
// Technique for the response. The price endpoint returns a cost breakdown
// (a superset of Technique). We type the breakdown manually since the
// generated schema for these endpoints only shows Technique as response.
// ---------------------------------------------------------------------------

/** One dimension of the technique cost breakdown. */
export interface TechniqueCostLine {
  dimension: string;
  label: string;
  power_cost: number;
}

/** Full cost breakdown returned by the price endpoint and bundled into the author response. */
export interface TechniqueCostBreakdown {
  tier: number;
  budget: number;
  gross_cost: number;
  refund: number;
  total_cost: number;
  within_budget: boolean;
  lines: TechniqueCostLine[];
}

// ---------------------------------------------------------------------------
// Power Ledger — per-stage breakdown of a cast's power, plus final total.
//
// Returned (generated cleanly) as part of the cast result payload.
// ---------------------------------------------------------------------------

export type PowerLedger = components['schemas']['PowerLedger'];
export type PowerLedgerEntry = components['schemas']['PowerLedgerEntry'];

// ---------------------------------------------------------------------------
// Pending alterations (Mage Scars), #877
// ---------------------------------------------------------------------------

export type PendingAlteration = components['schemas']['PendingAlteration'];
export type PaginatedPendingAlterationList =
  components['schemas']['PaginatedPendingAlterationList'];
export type AlterationLibraryEntry = components['schemas']['LibraryEntry'];
export type AlterationResolveResponse = components['schemas']['AlterationResolutionResponse'];

/**
 * The resolve endpoint accepts two mutually exclusive payload shapes. The
 * generated AlterationResolutionRequest can't express this — its
 * default-valued magnitude fields are non-optional, which would force the
 * library pick to carry scratch-path fields. Local union instead; wire
 * contract: AlterationResolutionSerializer (src/world/magic/serializers.py).
 */
export interface AlterationLibraryPickPayload {
  library_template_id: number;
}

/**
 * Scratch-path payload for POST /api/magic/pending-alterations/{id}/resolve/.
 *
 * `parent_template_id` (lineage) is deliberately omitted — staff-only concept
 * with no player-facing flow; the wire schema accepts it but this surface never
 * sends it.
 */
export interface AlterationScratchPayload {
  name: string;
  player_description: string;
  observer_description: string;
  weakness_damage_type_id: number | null;
  weakness_magnitude: number;
  resonance_bonus_magnitude: number;
  social_reactivity_magnitude: number;
  is_visible_at_rest: boolean;
}

export type AlterationResolvePayload = AlterationLibraryPickPayload | AlterationScratchPayload;

// ---------------------------------------------------------------------------
// Entry-flourish offers, #1140
// ---------------------------------------------------------------------------

export type PendingEntryFlourishOffer = components['schemas']['PendingEntryFlourishOffer'];
export type PaginatedPendingEntryFlourishOfferList =
  components['schemas']['PaginatedPendingEntryFlourishOfferList'];

// Body for POST /api/magic/entry-flourish/respond/ + result.
// Generated via @extend_schema on EntryFlourishRespondView (#1140).
export type EntryFlourishRespondRequest = components['schemas']['EntryFlourishRespondRequest'];
export type EntryFlourishResult = components['schemas']['EntryFlourishResult'];

// ---------------------------------------------------------------------------
// Audere offers, #873
// ---------------------------------------------------------------------------

export type PendingAudereOffer = components['schemas']['PendingAudereOffer'];
export type PaginatedPendingAudereOfferList =
  components['schemas']['PaginatedPendingAudereOfferList'];

// Body for POST /api/magic/audere/respond/ (accept=false declines) + result.
// Generated via @extend_schema on AudereRespondView (#920).
export type AudereRespondRequest = components['schemas']['AudereRespondRequest'];
export type AudereOfferResult = components['schemas']['AudereOfferResult'];

// ---------------------------------------------------------------------------
// Audere Majora (Crossing offer), #543 — generated shapes (#920)
//
// The PendingAudereMajoraOfferViewSet is auto-detected by drf-spectacular;
// `eligible_paths` is now typed via @extend_schema_field on the serializer's
// get_eligible_paths, so the whole offer (and its paginated list) re-export
// cleanly. The respond endpoint is annotated via @extend_schema.
// ---------------------------------------------------------------------------

export type EligiblePath = components['schemas']['EligiblePath'];
export type PendingAudereMajoraOffer = components['schemas']['PendingAudereMajoraOffer'];
export type PaginatedPendingAudereMajoraOfferList =
  components['schemas']['PaginatedPendingAudereMajoraOfferList'];

export type AudereMajoraRespondRequest = components['schemas']['AudereMajoraRespondRequest'];
export type AudereMajoraCrossingResult = components['schemas']['AudereMajoraCrossingResult'];

export type PathOptions = components['schemas']['PathOptions'];
export type PathListItem = components['schemas']['PathList'];

/** A declared path intent as returned by GET /api/progression/path-intent/. */
export interface PathIntentDetail {
  id: number;
  intended_path: EligiblePath & Record<string, unknown>;
  declared_at: string;
}

/** Response shape for GET /api/progression/path-intent/. */
export interface PathIntentResponse {
  intent: PathIntentDetail | null;
}

/**
 * tier_caps is a SerializerMethodField, so the generated schema leaves it as
 * `{ [key: string]: unknown }`. Shape source of truth:
 * ALTERATION_TIER_CAPS in src/world/magic/constants.py.
 */
export interface AlterationTierCaps {
  social_cap: number;
  weakness_cap: number;
  resonance_cap: number;
  visibility_required: boolean;
}

export function getTierCaps(pending: PendingAlteration): AlterationTierCaps {
  return pending.tier_caps as unknown as AlterationTierCaps;
}

/** Mirrors MIN_ALTERATION_DESCRIPTION_LENGTH in src/world/magic/constants.py. */
export const MIN_ALTERATION_DESCRIPTION_LENGTH = 40;

/** Request body for POST /api/magic/techniques/price/ and /api/magic/techniques/author/. */
export interface TechniqueDesignRequest {
  name: string;
  description: string;
  gift_id: number;
  style_id: number;
  effect_type_id: number;
  action_category: string;
  tier: number;
  intensity: number;
  control: number;
  anima_cost: number;
  restriction_ids?: number[];
  capability_grants?: {
    capability_id: number;
    base_value?: number;
    intensity_multiplier?: number;
  }[];
  damage_profiles?: {
    damage_type_id: number | null;
    base_damage?: number;
    damage_intensity_multiplier?: number;
  }[];
  applied_conditions?: {
    condition_id: number;
    base_severity?: number;
    base_duration_rounds?: number | null;
  }[];
  character_id?: number;
}
