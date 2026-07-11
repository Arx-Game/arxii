/**
 * Shared types for the ActionDeclarationCard and related action UI.
 *
 * Lives in frontend/src/actions/ — a new top-level module used by both
 * scenes and combat. See docs/superpowers/specs/2026-05-23-unified-combat-ui-design.md §4.
 */

export type EffortLevel = 'VERY_LOW' | 'LOW' | 'MEDIUM' | 'HIGH' | 'VERY_HIGH';

export type ActionSlot =
  | 'focused'
  | 'passive-physical'
  | 'passive-social'
  | 'passive-mental'
  | 'scene'; // single-card scene context

export interface ActionContext {
  slot: ActionSlot;
  /** Technique PK selected for this action. */
  techniqueId?: number;
  targetKind?: 'opponent' | 'ally' | 'social' | 'self';
  /**
   * Selected target's PK. In combat this is the dispatch PK — a CombatOpponent
   * PK when targetKind is 'opponent', a CombatParticipant PK when 'ally' —
   * threaded to the dispatch as focused_opponent_target_id / focused_ally_target_id.
   */
  targetId?: number;
  effort: EffortLevel;
  strainCommitment: number;
}

/**
 * Cast-time position-targeting shape for a technique (#2206). Mirrors the
 * backend `position_target_shape` value: "none" (no position target),
 * "single" (one destination position), or "pair" (two positions, e.g. an
 * origin/destination pair).
 */
export type PositionTargetShape = 'none' | 'single' | 'pair';

/**
 * Cast-time position selection for a technique whose `PositionTargetShape`
 * is "single" or "pair" (#2206). Lifted in `YourTurn`, threaded into the
 * focused `ActionDeclarationCard` via props (`castPosition` /
 * `onCastPositionChange`); merged into the focused dispatch's kwargs as
 * `position_params` on submit.
 */
export interface CastPosition {
  destinationId?: number;
  pairA?: number;
  pairB?: number;
}

/**
 * One selectable combatant in the focused-target picker (#1001a). The shared
 * ActionDeclarationCard receives these from the combat panel; scene usage omits
 * them and falls back to the kind-only selector.
 */
export interface TargetOption {
  /** Dispatch PK: CombatOpponent PK (opponent) or CombatParticipant PK (ally). */
  id: number;
  kind: 'opponent' | 'ally';
  name: string;
  /**
   * The combatant's in-world ObjectDB pk, used for the applicable-pulls API
   * (target_object_id). Present for opponents; null/undefined otherwise.
   */
  objectId?: number | null;
  /**
   * The combatant's current position PK — used by the reach pre-filter (#532)
   * to disable targets outside the selected technique's reach. Absent/null means
   * "unplaced": the reach check treats unplaced combatants as always reachable
   * (lenient, matching the backend's technique_can_reach).
   */
  positionId?: number | null;
}
