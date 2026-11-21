/**
 * The Gift stage's resonance picks (#5231): pure helpers over `draft_data.gift_resonance_weights`,
 * the list of `{resonance_id, weight}` the creation points are spread across.
 *
 * The rule the server enforces: one Primal resonance (the feeling that gives the character
 * strength), at most one more from a single outward side (Celestial for helping others,
 * Abyssal for hurting them), every pick holding at least one point, and the points adding
 * up to the budget. (The server also accepts a second pick saved before the feeling, as a
 * list of that one pick holding every point.) These helpers read a saved list into the three
 * answers the step asks and write the answers back as a list that always obeys that rule, so
 * the step never sends a list the server refuses. A draft saved under the old rule, or with
 * points left unplaced, reads as no answers, so the player sees nothing chosen and picks again.
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
  /** The answer about other people; null until one is given. */
  lean: Lean | null;
  /** The second pick, from the side `lean` names; null with no second pick. */
  outward: number | null;
  /**
   * The points on the Primal pick when both picks exist; the rest of the budget is on the
   * second pick. Outside 1 to budget minus 1 it means "not split yet" and the default split
   * is used.
   */
  primalPoints: number;
};

/** The affinity of a Celestial or Abyssal side. */
export type OutwardAffinity = typeof AFFINITY_CELESTIAL | typeof AFFINITY_ABYSSAL;

/** The affinity a side's resonances belong to. */
export function affinityOfLean(lean: 'give' | 'take'): OutwardAffinity {
  return lean === 'give' ? AFFINITY_CELESTIAL : AFFINITY_ABYSSAL;
}

/** The points placed so far across every pick. */
function placedPoints(weights: ResonanceWeightPick[]): number {
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

/** The picks nothing has been chosen for. */
function noPicks(budget: number): StrengthPicks {
  return { primal: null, lean: null, outward: null, primalPoints: budget };
}

/** The points the feeling keeps when a second pick is first added: the demo's 7 of 10. */
export function defaultPrimalPoints(budget: number): number {
  return budget - Math.max(1, Math.round(budget * 0.3));
}

/**
 * The answers a saved list holds, or null when the list is not one the step writes: more than
 * two picks, two Primal picks, a Celestial and an Abyssal pick together, any other resonance,
 * a pick under one point, or points that do not add up to `budget`. A list holding only a
 * Primal pick, only a second pick, or both is readable.
 */
function readList(
  weights: ResonanceWeightPick[],
  resonances: Resonance[],
  budget: number
): StrengthPicks | null {
  if (weights.length < 1 || weights.length > 2) return null;
  if (!weights.every((pick) => Number.isInteger(pick.weight) && pick.weight >= 1)) return null;
  if (placedPoints(weights) !== budget) return null;
  const affinity = affinityNames(resonances);
  const primals = weights.filter((pick) => affinity.get(pick.resonance_id) === AFFINITY_PRIMAL);
  const outwards = weights.filter((pick) => isOutward(affinity.get(pick.resonance_id)));
  if (primals.length > 1 || outwards.length > 1) return null;
  if (primals.length + outwards.length !== weights.length) return null;
  const [primal] = primals;
  const [outward] = outwards;
  let lean: Lean | null = primal ? 'none' : null;
  if (outward) lean = affinity.get(outward.resonance_id) === AFFINITY_CELESTIAL ? 'give' : 'take';
  let primalPoints = 0;
  if (primal) primalPoints = outward ? primal.weight : budget;
  return {
    primal: primal?.resonance_id ?? null,
    lean,
    outward: outward?.resonance_id ?? null,
    primalPoints,
  };
}

/**
 * The answers a saved list holds. A list that breaks the rule or does not place every point
 * holds no answers, so nothing shows as chosen and the player picks again.
 */
export function picksFromWeights(
  weights: ResonanceWeightPick[],
  resonances: Resonance[],
  budget: number
): StrengthPicks {
  return readList(weights, resonances, budget) ?? noPicks(budget);
}

/**
 * The list the answers make, the Primal pick first, always one the server accepts: nothing
 * chosen saves an empty list; one pick holds all `budget` points; two picks split the budget
 * at `primalPoints`. Neither as the answer drops any second pick.
 */
export function weightsFromPicks(p: StrengthPicks, budget: number): ResonanceWeightPick[] {
  const outward = p.lean === 'none' ? null : p.outward;
  if (p.primal == null && outward == null) return [];
  if (p.primal == null) return [{ resonance_id: outward as number, weight: budget }];
  if (outward == null) return [{ resonance_id: p.primal, weight: budget }];
  const split =
    p.primalPoints >= 1 && p.primalPoints <= budget - 1
      ? p.primalPoints
      : defaultPrimalPoints(budget);
  return [
    { resonance_id: p.primal, weight: split },
    { resonance_id: outward, weight: budget - split },
  ];
}

/**
 * Whether a saved list is a finished answer: exactly one Primal pick, at most one more from
 * the Celestial or Abyssal side, every weight at least one, the points summing to `budget`.
 */
export function strengthPicksComplete(
  weights: ResonanceWeightPick[],
  resonances: Resonance[],
  budget: number
): boolean {
  return readList(weights, resonances, budget)?.primal != null;
}

/**
 * The affinity the answers name the aura after, once both picks exist. Primal with no second
 * pick, and on an even split; otherwise the side holding more of the points.
 */
export function mainAffinityOf(
  p: StrengthPicks,
  budget: number
): typeof AFFINITY_PRIMAL | OutwardAffinity {
  if (p.lean == null || p.lean === 'none' || p.outward == null) return AFFINITY_PRIMAL;
  if (p.primalPoints >= budget - p.primalPoints) return AFFINITY_PRIMAL;
  return affinityOfLean(p.lean);
}
