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
 * @param reach            The technique's reach string ("same" | "adjacent" | "any" | "reach_n" | null).
 * @param actorPositionId  The actor's current position PK, or null/undefined if unplaced.
 * @param targetPositionId The target's current position PK, or null/undefined if unplaced.
 * @param adjacency        The encounter's position adjacency graph (EncounterDetail.position_adjacency).
 * @param reachHops        When reach is "reach_n", the max BFS hops (default 1).
 */
export function isTargetReachable(
  reach: string | null | undefined,
  actorPositionId: number | null | undefined,
  targetPositionId: number | null | undefined,
  adjacency: PositionAdjacencyItem[],
  reachHops?: number | null
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

  // "reach_n" — bounded BFS over the adjacency graph up to reachHops hops.
  if (reach === 'reach_n') {
    const maxHops = reachHops ?? 1;
    if (targetPositionId === actorPositionId) return true;
    return isReachableWithinHops(adjacency, actorPositionId, targetPositionId, maxHops);
  }

  // Unknown reach values — default to reachable (safe/lenient).
  return true;
}

/**
 * Returns true when a candidate *position* (rather than an occupant) is
 * reachable by the actor given the technique's reach constraint (#2206) —
 * used by the cast-time position picker's "single" shape.
 *
 * A position is its own "target position," so this is a thin, self-documenting
 * wrapper around `isTargetReachable`: no occupant/persona lookup is needed,
 * the candidate position's own id is passed directly as the target position id.
 */
export function isPositionReachable(
  reach: string | null | undefined,
  actorPositionId: number | null | undefined,
  candidatePositionId: number | null | undefined,
  adjacency: PositionAdjacencyItem[],
  reachHops?: number | null
): boolean {
  return isTargetReachable(reach, actorPositionId, candidatePositionId, adjacency, reachHops);
}

/**
 * Bounded BFS over the adjacency graph. Returns true if `targetPositionId`
 * is reachable from `startPositionId` within `maxHops` edges.
 */
function isReachableWithinHops(
  adjacency: PositionAdjacencyItem[],
  startPositionId: number,
  targetPositionId: number,
  maxHops: number
): boolean {
  const visited = new Set<number>([startPositionId]);
  const frontier: Array<{ id: number; depth: number }> = [{ id: startPositionId, depth: 0 }];

  while (frontier.length > 0) {
    const { id, depth } = frontier.shift()!;
    if (depth >= maxHops) continue;

    const entry = adjacency.find((a) => a.position_id === id);
    const neighbors = entry?.adjacent_position_ids ?? [];
    for (const neighborId of neighbors) {
      if (neighborId === targetPositionId) return true;
      if (!visited.has(neighborId)) {
        visited.add(neighborId);
        frontier.push({ id: neighborId, depth: depth + 1 });
      }
    }
  }
  return false;
}
