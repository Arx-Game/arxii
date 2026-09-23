/**
 * Founder Almanach step/tier helpers (#3983 Plan B Task 4). `TIER_RANK`
 * mirrors `ladder/tree.ts`'s `TIER_ORDER` (which itself mirrors
 * `world.societies.houses.constants.TitleTier`, #3091) as a numeric rank —
 * the Claim gate on `SeatPicker`'s trailing column compares a row's tier
 * rank against the founder's Upbringing ceiling
 * (`OriginTemplate.max_claim_tier`). Duplicated here rather than exported
 * from `ladder/tree.ts` (that file is Plan A Task 8's, outside this task's
 * file scope) — six literal entries, unlikely to drift since `TitleTier`
 * itself is a closed, rarely-touched enum.
 */
import type { LadderRow } from '../types';

export type FounderStep = 'seat' | 'house' | 'family' | 'land' | 'estate' | 'record';

/** Shallowest (biggest) tier ranks highest, mirroring `TIER_ORDER`'s order. */
export const TIER_RANK: Record<string, number> = {
  empire: 6,
  kingdom: 5,
  duchy: 4,
  march: 3,
  county: 2,
  barony: 1,
};

/**
 * The founder's Claim ceiling as a rank number: a blank `max_claim_tier`
 * (no Upbringing restriction, or a fixture built before Task 3 wires the
 * field up) permits every tier — 99 sits above every real `TIER_RANK` value.
 */
export function permittedRank(maxClaimTier: string | undefined): number {
  if (!maxClaimTier) return 99;
  return TIER_RANK[maxClaimTier] ?? 99;
}

/** Whether `row`'s own tier is at or under the founder's Claim ceiling. */
export function withinClaimGate(row: LadderRow, permitted: number): boolean {
  return (TIER_RANK[row.tier] ?? 0) <= permitted;
}

/** One entry in the Founder Almanach's contents rail (plates F-I onward
 * `.contents`) — `group` is the rail's `.mv .label`, `step` the chapter it
 * opens, `label` the `<li>` text. */
export interface FounderContentsEntry {
  group: string;
  step: FounderStep;
  label: string;
}

export const FOUNDER_CONTENTS: FounderContentsEntry[] = [
  { group: 'Holdings', step: 'seat', label: 'The Seat' },
  { group: 'House', step: 'house', label: 'The House' },
  { group: 'House', step: 'family', label: 'The Family' },
  { group: 'Holdings', step: 'land', label: 'The Land' },
  { group: 'Holdings', step: 'estate', label: 'The Estate' },
];
