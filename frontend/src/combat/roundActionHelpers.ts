/**
 * Pure helpers over the viewer's PlayerActions for the combat panel (#4608).
 */

import type { PlayerAction } from '@/scenes/actionTypes';

/**
 * The registry actions that move the viewer during a round (#4663): a step, a take-off,
 * a landing, a pass roll into held ground, and a stunt
 * (#4675, panel-only: the battle map ignores it for map clicks).
 */
export const MOVE_REGISTRY_KEYS: ReadonlySet<string> = new Set([
  'move_to_position',
  'take_flight',
  'land',
  'pass_held_ground',
  'perform_stunt',
]);

/** A registry action that moves the viewer (see MOVE_REGISTRY_KEYS). */
export function isMoveAction(a: PlayerAction): boolean {
  return (
    a.is_movement === true ||
    (a.ref.backend === 'registry' &&
      a.ref.registry_key != null &&
      MOVE_REGISTRY_KEYS.has(a.ref.registry_key))
  );
}

/**
 * A registry entry the generic action lists (the scene ActionPanel, the composer's
 * ActionAttachment) must not show (#4675): a move, stunt, pass or GM placement names
 * its place or feature in its ref, which a generic button drops; the GM's Add feature
 * needs a place and a feature type picked. They live on the map and the combat panels.
 */
export function isMapOnlyAction(a: PlayerAction): boolean {
  return (
    a.ref.backend === 'registry' &&
    (a.ref.position_id != null ||
      a.ref.feature_id != null ||
      a.ref.registry_key === 'gm_attach_feature')
  );
}

const HOPS_LINE = /^\d+ hops? left this round\.$/;

/**
 * The viewer's hops left this round, as the server words it on the moves it offers
 * ("1 hop left this round."), or null outside a declaring round or when moves are refused.
 * Any offered move may carry it; a held place's note or a pass's approach does not (#4663).
 */
export function hopsLeftLine(actions: PlayerAction[]): string | null {
  const line = actions.find(
    (a) => isMoveAction(a) && a.prerequisite_met && HOPS_LINE.test(a.description)
  );
  return line ? line.description : null;
}

/** Techniques a waiting strike can hold: combat casts reaching the same or the next position. */
export function waitingStrikeTechniques(actions: PlayerAction[]): PlayerAction[] {
  return actions.filter(
    (a) =>
      a.ref.backend === 'combat' &&
      a.ref.technique_id != null &&
      (a.reach === 'same' || a.reach === 'adjacent')
  );
}
