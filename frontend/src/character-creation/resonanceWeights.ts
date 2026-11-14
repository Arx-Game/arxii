/**
 * The Gift stage's resonance picks (#5123): pure helpers over `draft_data.gift_resonance_weights`,
 * the list of `{resonance_id, weight}` a new character spreads their creation points across.
 * The server owns the rules (a pick needs at least one point, none twice, never more than
 * the creation points); these only keep the stepper in step with them.
 */

import type { ResonanceWeightPick } from './types';

/** The points placed so far across every pick. */
export function placedPoints(weights: ResonanceWeightPick[]): number {
  return weights.reduce((sum, pick) => sum + pick.weight, 0);
}

/** The points on one resonance, 0 when it is not picked. */
export function weightOf(weights: ResonanceWeightPick[], resonanceId: number): number {
  return weights.find((pick) => pick.resonance_id === resonanceId)?.weight ?? 0;
}

/**
 * The picks with one resonance moved to `weight`. A pick keeps its place in the list; a new
 * one goes last; a weight under one drops the pick, since the server refuses a pick with
 * no points.
 */
export function withWeight(
  weights: ResonanceWeightPick[],
  resonanceId: number,
  weight: number
): ResonanceWeightPick[] {
  const held = weights.some((pick) => pick.resonance_id === resonanceId);
  if (weight < 1) return weights.filter((pick) => pick.resonance_id !== resonanceId);
  if (!held) return [...weights, { resonance_id: resonanceId, weight }];
  return weights.map((pick) => (pick.resonance_id === resonanceId ? { ...pick, weight } : pick));
}

/** The picks heaviest first, an earlier pick winning a tie (the server's own order). */
export function heaviestFirst(weights: ResonanceWeightPick[]): ResonanceWeightPick[] {
  return [...weights].sort((a, b) => b.weight - a.weight);
}

/** The heaviest pick's resonance id, or null with no picks: the one the server reads from. */
export function leadResonanceId(weights: ResonanceWeightPick[]): number | null {
  return heaviestFirst(weights)[0]?.resonance_id ?? null;
}
