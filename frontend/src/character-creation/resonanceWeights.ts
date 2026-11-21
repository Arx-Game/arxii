/**
 * The Gift stage's resonance picks (#5231): pure helpers over `draft_data.gift_resonance_weights`,
 * the list of `{resonance_id, weight}` the creation points are spread across.
 *
 * The rule the server enforces: one Primal resonance (the feeling that gives the character
 * strength), at most one more from a single outward side (Celestial for helping others,
 * Abyssal for hurting them), every pick holding at least one point, and the points adding
 * up to the budget. These helpers read a saved list into the three answers the step asks
 * and write the answers back as a list that always obeys that rule, so the step never sends
 * a list the server refuses. A draft saved under the old rule (any number of picks) is read
 * for the first Primal pick and the first outward pick, and the rest is ignored.
 */

import type { Resonance, ResonanceWeightPick } from './types';

const AFFINITY_PRIMAL = 'Primal';
const AFFINITY_CELESTIAL = 'Celestial';
const AFFINITY_ABYSSAL = 'Abyssal';

/** The side the second pick comes from: helping others, hurting them, or no second pick. */
export type Lean = 'give' | 'take' | 'none';

/** The three answers the step asks, as the picks and the balance they make. */
export type StrengthPicks = {
  /** The Primal resonance that gives strength, or null before one is chosen. */
  primal: number | null;
  lean: Lean;
  /** The second pick, from the side `lean` names; null with no second pick. */
  outward: number | null;
  /** The points on the Primal pick; the rest of the budget is on the second pick. */
  primalPoints: number;
};

/** The affinity of a Celestial or Abyssal side. */
export type OutwardAffinity = typeof AFFINITY_CELESTIAL | typeof AFFINITY_ABYSSAL;

/** The affinity a side's resonances belong to. */
export function affinityOfLean(lean: 'give' | 'take'): OutwardAffinity {
  return lean === 'give' ? AFFINITY_CELESTIAL : AFFINITY_ABYSSAL;
}

/** The points placed so far across every pick. */
export function placedPoints(weights: ResonanceWeightPick[]): number {
  return weights.reduce((sum, pick) => sum + pick.weight, 0);
}

/** The picks heaviest first, an earlier pick winning a tie (the server's own order). */
export function heaviestFirst(weights: ResonanceWeightPick[]): ResonanceWeightPick[] {
  return [...weights].sort((a, b) => b.weight - a.weight);
}

/** The heaviest pick's resonance id, or null with no picks: the one the server reads from. */
export function leadResonanceId(weights: ResonanceWeightPick[]): number | null {
  return heaviestFirst(weights)[0]?.resonance_id ?? null;
}

function affinityNames(resonances: Resonance[]): Map<number, string> {
  return new Map(resonances.map((resonance) => [resonance.id, resonance.affinity_name]));
}

function isOutward(affinity: string | undefined): boolean {
  return affinity === AFFINITY_CELESTIAL || affinity === AFFINITY_ABYSSAL;
}

/**
 * The answers a saved list holds: the first Primal pick, and the first Celestial or Abyssal
 * pick with the side it names. Anything an old draft holds beyond those two is left out, so
 * nothing the rule forbids shows as chosen. With no second pick the Primal pick holds every
 * point.
 */
export function picksFromWeights(
  weights: ResonanceWeightPick[],
  resonances: Resonance[],
  budget: number
): StrengthPicks {
  const affinity = affinityNames(resonances);
  const primalPick = weights.find((pick) => affinity.get(pick.resonance_id) === AFFINITY_PRIMAL);
  const outwardPick = weights.find((pick) => isOutward(affinity.get(pick.resonance_id)));
  if (!primalPick) return { primal: null, lean: 'none', outward: null, primalPoints: budget };
  if (!outwardPick) {
    return { primal: primalPick.resonance_id, lean: 'none', outward: null, primalPoints: budget };
  }
  return {
    primal: primalPick.resonance_id,
    lean: affinity.get(outwardPick.resonance_id) === AFFINITY_CELESTIAL ? 'give' : 'take',
    outward: outwardPick.resonance_id,
    primalPoints: Math.min(Math.max(primalPick.weight, 1), budget - 1),
  };
}

/**
 * The list the answers make, the Primal pick first. With no feeling chosen there is nothing to
 * save. With no second pick the Primal pick holds all `budget` points; with one the two split
 * the budget at `primalPoints`.
 */
export function weightsFromPicks(p: StrengthPicks, budget: number): ResonanceWeightPick[] {
  if (p.primal == null) return [];
  if (p.lean === 'none' || p.outward == null) return [{ resonance_id: p.primal, weight: budget }];
  return [
    { resonance_id: p.primal, weight: p.primalPoints },
    { resonance_id: p.outward, weight: budget - p.primalPoints },
  ];
}

/**
 * Whether a saved list obeys the rule: exactly one Primal pick, at most one more from the
 * Celestial or Abyssal side, no other resonance, every weight a whole number of at least one,
 * and the points summing to `budget`.
 */
export function strengthPicksComplete(
  weights: ResonanceWeightPick[],
  resonances: Resonance[],
  budget: number
): boolean {
  const affinity = affinityNames(resonances);
  const primal = weights.filter((pick) => affinity.get(pick.resonance_id) === AFFINITY_PRIMAL);
  const outward = weights.filter((pick) => isOutward(affinity.get(pick.resonance_id)));
  if (primal.length !== 1 || outward.length > 1) return false;
  if (primal.length + outward.length !== weights.length) return false;
  if (!weights.every((pick) => Number.isInteger(pick.weight) && pick.weight >= 1)) return false;
  return placedPoints(weights) === budget;
}

/**
 * The affinity the answers name the aura after. Primal with no second pick, and on an even
 * split; otherwise the side holding more of the points.
 */
export function mainAffinityOf(
  p: StrengthPicks,
  budget: number
): typeof AFFINITY_PRIMAL | OutwardAffinity {
  if (p.lean === 'none' || p.outward == null || p.primalPoints >= budget - p.primalPoints) {
    return AFFINITY_PRIMAL;
  }
  return affinityOfLean(p.lean);
}
