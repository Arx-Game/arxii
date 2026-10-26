/**
 * Shared helpers for dodging and area attacks (#4676): the dodge-plan request, the
 * attacks covering a place, and the telegraph's line.
 */

import type { DispatchActionRequest, PendingAttack } from './types';

export const DODGE_REGISTRY_KEY = 'combat_dodge';

/** A `combat_dodge` registry dispatch with these kwargs. */
export function dodgeRequest(kwargs: Record<string, unknown>): DispatchActionRequest {
  return { ref: { backend: 'registry', registry_key: DODGE_REGISTRY_KEY }, kwargs };
}

/** The pending attacks that will cover the place with this id. */
export function attacksCoveringPlace(
  attacks: PendingAttack[],
  positionId: number | null
): PendingAttack[] {
  if (positionId === null) return [];
  return attacks.filter((a) => !a.cancelled && a.covered_position_id === positionId);
}

/** "Holy fire lands here at the end of this round." and its later variants. */
export function telegraphLine(attackName: string, roundsUntilLanding: number): string {
  if (roundsUntilLanding <= 0) return `${attackName} lands here at the end of this round`;
  if (roundsUntilLanding === 1) return `${attackName} lands here next round`;
  return `${attackName} lands here in ${roundsUntilLanding} rounds`;
}
