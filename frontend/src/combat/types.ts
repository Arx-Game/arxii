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

/** One participant's mark on an opponent this round (#4603). */
export type CombatMark = components['schemas']['CombatMark'];

/** Cached encounter fixtures may predate the companion-order and mark projections. */
export type EncounterDetail = Omit<
  components['schemas']['EncounterDetail'],
  | 'companion_orders'
  | 'pending_selections'
  | 'sustained_actions'
  | 'protection_commitments'
  | 'marks'
> & {
  marks?: components['schemas']['EncounterDetail']['marks'];
  pending_selections?: components['schemas']['EncounterDetail']['pending_selections'];
  sustained_actions?: components['schemas']['EncounterDetail']['sustained_actions'];
  protection_commitments?: components['schemas']['EncounterDetail']['protection_commitments'];
  companion_orders?: components['schemas']['EncounterDetail']['companion_orders'];
};

// engagement_locks is schema-typed via @extend_schema_field (#3386) — a real
// component, not {[key: string]: unknown}[]. Active foil-duel pairings for
// the encounter.
export type EngagementLock = components['schemas']['EngagementLock'];

// pending_attacks is schema-typed via @extend_schema_field (#3572) - a real
// component, not {[key: string]: unknown}[]. Telegraphed NPC wind-ups not yet
// landed, soonest-landing first.
export type PendingAttack = components['schemas']['PendingAttack'];

// current_round_actions is typed as {[key: string]: unknown}[] in the schema —
// the backend serializes these with varying shapes depending on action type.
// For Phase 7 we surface them as opaque blobs; a typed shape is a follow-up.
export type RoundAction = Record<string, unknown>;

// surge_beats is schema-typed (SurgeBeatSerializer, #4737). Every viewer gets `id` and
// `narration`; the rest, roll fields included, reach only the surged participant's owner,
// GMs and staff, and the roll fields only for a rolled surge - so all of them are optional.
export type SurgeBeatTyped = components['schemas']['SurgeBeat'];

/**
 * Typed overlay for RoundAction entries from RoundActionSerializer.
 * Extends the opaque blob with the fields we actually consume in the UI.
 * maneuver: null = no special maneuver; "flee" / "cover" / "interpose" (#2207,
 * "Guard" in the UI) / "await_opening" (the waiting strike, #4608) = declared maneuver.
 * focused_ally_target: CombatParticipant PK of the covered/guarded ally
 * (cover/interpose only — null on interpose means "guard whoever is hit").
 */
export interface RoundActionTyped extends RoundAction {
  participant: number;
  participant_name: string;
  is_ready: boolean;
  maneuver: 'flee' | 'cover' | 'interpose' | 'await_opening' | null;
  focused_ally_target: number | null;
  /** Technique PK of the declared focused action (the held strike for "await_opening"). */
  focused_action?: number | null;
  /** ComboDefinition PK when this round's action has been upgraded to a combo, else null (#3381). */
  combo_upgrade: number | null;
}

// ---------------------------------------------------------------------------
// ClashState (from ClashStateSerializer, Phase 8)
//
// clashes is now correctly typed in the generated schema (the backend
// annotates get_clashes with @extend_schema_field, and get_contributors
// with its own ClashContributorSerializer), so these are direct re-exports
// of the generated components (#2423).
// ---------------------------------------------------------------------------

export type ClashContributor = components['schemas']['ClashContributor'];

export type ClashState = components['schemas']['ClashState'];

// ---------------------------------------------------------------------------
// Round combos (#3553)
//
// GET /api/combat/{id}/available_combos/ → RoundCombo[]: every combo taking
// shape this round, slot by slot. `complete` is the upgrade condition; a
// partial fill of a known combo lists which slots are still open.
// ---------------------------------------------------------------------------

export type RoundCombo = components['schemas']['RoundCombo'];

export type RoundComboSlot = components['schemas']['ComboSlotFill'];

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
  /** WORLD_INTERACTION target identity (#2503). */
  application_id?: number | null;
  target_object_id?: number | null;
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
