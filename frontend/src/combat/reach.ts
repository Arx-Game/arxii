/**
 * Reach pre-filter for the combat target picker (#532).
 *
 * A pure helper that decides whether a target is reachable given the selected
 * technique's reach constraint, the actor's position, the target's position, and
 * the room's adjacency graph.
 *
 * The backend enforces reach authoritatively; this is the UX layer — disabling
 * unreachable targets in the declaration UI before the player submits.
 */

import type { PositionAdjacencyItem } from './types';

/**
 * Returns true when the target is reachable by the actor given the technique's
 * reach constraint.
 *
 * Rules (mirrors backend `technique_can_reach`):
 * - reach == null or "any"          → always reachable (no constraint).
 * - actor or target positionId is null/undefined (unplaced) → always reachable
 *   (lenient — matching backend behaviour).
 * - "same"     → targetPositionId === actorPositionId.
 * - "adjacent" → targetPositionId === actorPositionId (same counts as adjacent),
 *                OR targetPositionId appears in the adjacency entry for
 *                actorPositionId.
 *
 * @param reach            The technique's reach string ("same" | "adjacent" | "any" | null).
 * @param actorPositionId  The actor's current position PK, or null/undefined if unplaced.
 * @param targetPositionId The target's current position PK, or null/undefined if unplaced.
 * @param adjacency        The encounter's position adjacency graph (EncounterDetail.position_adjacency).
 */
export function isTargetReachable(
  reach: string | null | undefined,
  actorPositionId: number | null | undefined,
  targetPositionId: number | null | undefined,
  adjacency: PositionAdjacencyItem[]
): boolean {
  // No constraint (or any) — always reachable.
  if (reach == null || reach === 'any') return true;

  // Unplaced actor or target — lenient, treat as reachable.
  if (actorPositionId == null || targetPositionId == null) return true;

  // "same" — must be in the same position.
  if (reach === 'same') return targetPositionId === actorPositionId;

  // "adjacent" — same position counts as adjacent; also check the adjacency graph.
  if (reach === 'adjacent') {
    if (targetPositionId === actorPositionId) return true;
    const entry = adjacency.find((a) => a.position_id === actorPositionId);
    return entry?.adjacent_position_ids.includes(targetPositionId) ?? false;
  }

  // Unknown reach values — default to reachable (safe/lenient).
  return true;
}
