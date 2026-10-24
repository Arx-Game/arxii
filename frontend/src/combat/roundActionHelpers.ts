/**
 * Pure helpers over the viewer's PlayerActions for the combat panel (#4608).
 */

import type { PlayerAction } from '@/scenes/actionTypes';

/**
 * The viewer's hops left this round, as the server words it on each move it offers
 * ("1 hop left this round."), or null outside a declaring round or when moves are refused.
 */
export function hopsLeftLine(actions: PlayerAction[]): string | null {
  const line = actions.find((a) => a.ref.registry_key === 'move_to_position');
  if (!line || !line.prerequisite_met || !line.description.includes('hop')) return null;
  return line.description;
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
