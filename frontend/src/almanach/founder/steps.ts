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

/** One chapter entry inside a Founder Almanach contents-rail group
 * (`FounderContentsGroup.entries`) — `step` the chapter it opens, `label`
 * the `<li>` text. */
export interface FounderContentsEntry {
  step: FounderStep;
  label: string;
}

/**
 * One `.mv` block of the Founder Almanach's contents rail (plates F-I
 * onward `.contents`) — `label` is the block's own `.mv .label` heading.
 * The plate carries THREE `.mv` blocks, not two: "Holdings" appears twice,
 * split by the "House" block between them (Holdings›Seat, then
 * House›House,Family, then Holdings›Land,Estate) — fix round 1, Finding 1:
 * grouping by label collapsed the two Holdings runs into one and reordered
 * Land/Estate ahead of House/Family. A literal list of groups, one per
 * plate `.mv`, makes that bug structurally impossible to reintroduce.
 */
export interface FounderContentsGroup {
  label: string;
  entries: FounderContentsEntry[];
}

export const FOUNDER_CONTENTS: FounderContentsGroup[] = [
  { label: 'Holdings', entries: [{ step: 'seat', label: 'The Seat' }] },
  {
    label: 'House',
    entries: [
      { step: 'house', label: 'The House' },
      { step: 'family', label: 'The Family' },
    ],
  },
  {
    label: 'Holdings',
    entries: [
      { step: 'land', label: 'The Land' },
      { step: 'estate', label: 'The Estate' },
    ],
  },
];
