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
import { STATES } from '../copy';
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

/**
 * Everything a claim on `titleId` grants (#3983 Plan B Task 6), mirroring
 * the backend's `claim_grants` (`world/societies/houses/almanach.py`)
 * client-side off the same ladder rows the Seat/Land chapters already fetch
 * — there is no per-claim "grants" read on the wire, so this has to be
 * derived from `LadderRow[]` rather than called.
 *
 * `claim_grants` groups titles by `seat_domain_id` (every title sharing one
 * physical seat — a duchy's own county and barony ride the same seat as the
 * duchy itself, `almanach.py`'s module docstring: "a count-or-higher rung
 * comes with the seat chain down to the barony that is its demesne").
 * `LadderRow` carries `seat_domain_id` too, but a non-top chain member's
 * `comes_with` is ALREADY that grouping resolved to a name (`almanach_reads
 * .py`: "a non-top row always reports its chain top's name via both
 * `comes_with` and `sworn_to`") — walking `parent_title_id` down from the
 * claimed row through rows whose `comes_with` names it reaches every
 * internal chain member without a second `seat_domain_id` pass.
 *
 * Extras are the backend's `loose` query: a houseless barony whose nearest
 * rung ancestor is one of the chain rows and which is not itself another
 * rung's own chain member (`comes_with === ''` — a barony that "comes with"
 * some OTHER county is that county's own seat, excluded the same way the
 * backend excludes it via `_family_top(...) == b.pk`).
 */
export function grantsOf(rows: LadderRow[], titleId: number): LadderRow[] {
  const claimedRow = rows.find((row) => row.title_id === titleId);
  if (!claimedRow) return [];

  const chain: LadderRow[] = [claimedRow];
  const frontier: number[] = [claimedRow.title_id];
  while (frontier.length > 0) {
    const parentId = frontier.pop() as number;
    for (const row of rows) {
      if (row.parent_title_id === parentId && row.comes_with === claimedRow.name) {
        chain.push(row);
        frontier.push(row.title_id);
      }
    }
  }

  const chainIds = new Set(chain.map((row) => row.title_id));
  const extras = rows.filter(
    (row) =>
      row.tier === 'barony' &&
      !chainIds.has(row.title_id) &&
      row.parent_title_id != null &&
      chainIds.has(row.parent_title_id) &&
      row.comes_with === '' &&
      row.state === STATES.unclaimed
  );

  return [...chain, ...extras];
}

/** The claimed rung's own facts the Land chapter and Record plate both
 * quote (#3983 Plan B Task 6): the claimed row itself, every barony
 * `grantsOf` grants (the Land leaf's table rows), and the chain's own seat
 * barony — the internal chain member sharing the claimed rung's own name in
 * `comes_with` (or the claimed row itself, when the claim IS a barony: a
 * bare barony claim has no internal chain member below it and is its own
 * seat, `comes_with === ''` like any other top row). */
export interface FounderLandFacts {
  topRow: LadderRow;
  baronies: LadderRow[];
  seatBarony: LadderRow | null;
}

export function landFactsOf(rows: LadderRow[], titleId: number): FounderLandFacts | null {
  const grants = grantsOf(rows, titleId);
  const topRow = grants[0];
  if (!topRow) return null;

  const baronies = grants.filter((row) => row.tier === 'barony');
  const seatBarony =
    topRow.tier === 'barony'
      ? topRow
      : (baronies.find((row) => row.comes_with === topRow.name) ?? null);

  return { topRow, baronies, seatBarony };
}

/** "the land" record line's own base clause (#3983 Plan B Task 6, plates
 * F-IV/F-VI's `.sofar`/`.val` rows): `<top> · <n> baronies · seat <name>,
 * <hall>`. Shared between `RecordSoFar`'s abbreviated line and
 * `FounderRecord`'s own fuller one (which appends land shapes/produces) so
 * the two never drift on the shared prefix. */
export function landBaseLine(
  facts: FounderLandFacts,
  lands: Record<number, { hall_name: string }>
): string {
  // A missing seat barony and a present-but-undefined one both print
  // "Undefined" — the two only diverge in the barony TABLE's own richer
  // three-way rendering (`FounderLandsLeaf`'s `rungCell`), not in this
  // plain-string line.
  const seatName =
    facts.seatBarony && facts.seatBarony.is_defined ? facts.seatBarony.name : 'Undefined';
  const hall = facts.seatBarony
    ? lands[facts.seatBarony.title_id]?.hall_name || 'Undefined'
    : 'Undefined';
  const count = facts.baronies.length;
  return `${facts.topRow.name} · ${count} ${count === 1 ? 'barony' : 'baronies'} · seat ${seatName}, ${hall}`;
}
