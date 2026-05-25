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

export type EncounterDetail = components['schemas']['EncounterDetail'];
export type EncounterListItem = components['schemas']['EncounterList'];
export type Participant = components['schemas']['Participant'];
export type Opponent = components['schemas']['Opponent'];

// current_round_actions is typed as {[key: string]: unknown}[] in the schema —
// the backend serializes these with varying shapes depending on action type.
// For Phase 7 we surface them as opaque blobs; a typed shape is a follow-up.
export type RoundAction = Record<string, unknown>;

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
}
