/**
 * Combat module types — re-exports from generated schema + local extensions.
 *
 * Phase 7 of the unified-combat-ui plan.
 * See: docs/superpowers/specs/2026-05-23-unified-combat-ui-design.md §6
 */

import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Re-exports from generated schema
// ---------------------------------------------------------------------------

export type EncounterListItem = components['schemas']['EncounterList'];
export type Participant = components['schemas']['Participant'];
export type Opponent = components['schemas']['Opponent'];
export type PositionSummary = components['schemas']['PositionSummary'];

// ---------------------------------------------------------------------------
// Position adjacency
//
// position_adjacency is now correctly typed in the generated schema (the
// backend annotates get_position_adjacency with @extend_schema_field), so
// EncounterDetail is a direct re-export. PositionAdjacencyItem is kept as a
// convenience alias for the reach pre-filter consumers.
// ---------------------------------------------------------------------------

export type PositionAdjacencyItem = components['schemas']['PositionAdjacencyItem'];

export type PositionNode = components['schemas']['PositionNode'];
export type PositionEdgeInfo = components['schemas']['PositionEdge'];

export type EncounterDetail = components['schemas']['EncounterDetail'];

// current_round_actions is typed as {[key: string]: unknown}[] in the schema —
// the backend serializes these with varying shapes depending on action type.
// For Phase 7 we surface them as opaque blobs; a typed shape is a follow-up.
export type RoundAction = Record<string, unknown>;

// surge_beats is typed as {[key: string]: unknown}[] in the schema — the
// backend serializes owner-scoped keys (trigger_kind/amount/participant)
// conditionally, so only `narration` is guaranteed present.
export type SurgeBeat = Record<string, unknown>;

export interface SurgeBeatTyped extends SurgeBeat {
  narration: string;
  trigger_kind?: string;
  amount?: number;
  participant?: number;
}

/**
 * Typed overlay for RoundAction entries from RoundActionSerializer.
 * Extends the opaque blob with the fields we actually consume in the UI.
 * maneuver: null = no special maneuver; "flee" / "cover" / "interpose" (#2207,
 * "Guard" in the UI) = declared maneuver.
 * focused_ally_target: CombatParticipant PK of the covered/guarded ally
 * (cover/interpose only — null on interpose means "guard whoever is hit").
 */
export interface RoundActionTyped extends RoundAction {
  participant: number;
  participant_name: string;
  is_ready: boolean;
  maneuver: 'flee' | 'cover' | 'interpose' | null;
  focused_ally_target: number | null;
}

// ---------------------------------------------------------------------------
// Local type for ClashState (from ClashStateSerializer, Phase 8)
//
// EncounterDetail.clashes is typed as {[key: string]: unknown}[] in the
// generated schema because ClashStateSerializer is a SerializerMethodField
// result. We declare the concrete shape here.
// ---------------------------------------------------------------------------

export interface ClashContributor {
  character_id: number | null;
  character_name: string;
  action_slot: string;
  progress_delta: number;
  anima: number;
}

export interface ClashState {
  id: number;
  flavor: 'CLASH' | 'LOCK' | 'WARD' | 'BREAK';
  status: 'ACTIVE' | 'RESOLVED';
  progress: number;
  pc_win_threshold: number;
  npc_win_threshold: number | null;
  npc_opponent: number;
  /** Per-PC contribution rollup (Phase 7). */
  contributors: ClashContributor[];
  /** "PC" / "NPC" / "EVEN" — Phase 7. */
  side_favored: 'PC' | 'NPC' | 'EVEN';
}

// ---------------------------------------------------------------------------
// Local types for available-combos
//
// GET /api/combat/{id}/available_combos/ → EncounterDetail (per generated schema),
// but the actual response is a list of combo descriptors.
// The backend EncounterViewSet.available_combos action returns the encounter
// detail (not a separate schema), so we type the actual payload locally here.
// ---------------------------------------------------------------------------

export interface AvailableCombo {
  combo_id: number;
  combo_name: string;
  known_by_participant: boolean;
  slot_count: number;
}

// ---------------------------------------------------------------------------
// Dispatch types (used by useDispatchPlayerAction)
// ---------------------------------------------------------------------------

/** Matches ActionRef serializer shape from the backend. */
export interface ActionRef {
  backend: string;
  challenge_instance_id?: number | null;
  approach_id?: number | null;
  technique_id?: number | null;
  registry_key?: string | null;
  clash_id?: number | null;
  clash_action_slot?: string | null;
  action_slot?: string | null;
  /** Destination position PK — present on move_to_position registry actions (#532). */
  position_id?: number | null;
}

/** POST /api/actions/characters/{id}/dispatch/ request body. */
export interface DispatchActionRequest {
  ref: ActionRef;
  kwargs: Record<string, unknown>;
}

/** POST /api/actions/characters/{id}/dispatch/ response body. */
export interface DispatchResult {
  backend: string;
  deferred: boolean;
  /** Short human string from the action's result (DispatchResultSerializer.message). */
  message?: string | null;
  /**
   * Business-rule outcome, distinct from HTTP status — the endpoint always
   * resolves 200 for a rejected action (only a structural ref error is a 400).
   * `false` on an honest failure (e.g. permission/validation rejection from a
   * REGISTRY `ActionResult`); `true`/`null`/`undefined` reads as success —
   * `null` covers a deferred dispatch or a backend with no boolean success
   * notion (e.g. CHALLENGE), and `undefined` covers pre-#2010 callers that
   * haven't been updated to read this field yet.
   */
  success?: boolean | null;
  /**
   * Minimal jsonable identifying-field bag from the action's result
   * (`DispatchResultSerializer.data` — e.g. `{battle_id, scene_id}` for
   * `create_battle`). `null`/absent when the action carries no such data or
   * the dispatch was deferred.
   */
  data?: Record<string, unknown> | null;
}

/**
 * `result.success === false` is the honest-failure wire signal (#2010 review):
 * the dispatch endpoint always resolves HTTP 200 for a business-rule rejection
 * (only a structural ref error is a 400), so every write path must check this
 * before flipping confirmed local state (#2423).
 */
export function isDispatchFailure(result: Pick<DispatchResult, 'success'>): boolean {
  return result.success === false;
}
