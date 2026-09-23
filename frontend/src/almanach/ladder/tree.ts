/**
 * Almanach ladder tree helpers (#3983 Task 8). `buildLadderTree` nests a
 * realm's flat `LadderRow` list (Task 8 decision 2: the API already carries
 * `parent_title_id`, so the client just groups by it — no server round trip
 * per expand). The tier constants mirror `world.societies.houses.constants.
 * TitleTier` (six consistent-noun steps, #3091) so the level bar and the
 * dialogs' tier pickers speak the same vocabulary as the backend enum.
 */
import type { LadderRow } from '../types';

/** Mirrors `TitleTier`'s member order (`constants.py`) — shallowest first. */
export const TIER_ORDER = ['empire', 'kingdom', 'duchy', 'march', 'county', 'barony'] as const;

export type Tier = (typeof TIER_ORDER)[number];

/**
 * Level-bar button labels (plate S-I `.lvl`): the duchy button reads
 * "Ducal", not "Duchy" — every other tier matches `TitleTier`'s display
 * label (`constants.py`) exactly.
 */
export const TIER_LABELS: Record<string, string> = {
  empire: 'Empire',
  kingdom: 'Kingdom',
  duchy: 'Ducal',
  march: 'March',
  county: 'County',
  barony: 'Barony',
};

const TIER_PLURALS: Record<string, string> = {
  empire: 'empires',
  kingdom: 'kingdoms',
  duchy: 'duchies',
  march: 'marches',
  county: 'counties',
  barony: 'baronies',
};

/** `tier` (singular) at `count === 1`, else its plural noun. */
export function tierNoun(tier: string, count: number): string {
  if (count === 1) return tier;
  return TIER_PLURALS[tier] ?? `${tier}s`;
}

function tierIndex(tier: string): number {
  return TIER_ORDER.indexOf(tier as Tier);
}

/**
 * March and county share one rung (`almanach.TIER_TO_AREA_LEVEL`: MARCH is a
 * county-tier holding) — a march row displays, counts and expands exactly
 * like a county row (level-bar review ruling, #3983 Task 8 fix round 1: a
 * realm with no march titles must never grow a phantom March button).
 */
function displayTier(tier: string): string {
  return tier === 'march' ? 'county' : tier;
}

export interface LadderTreeNode {
  row: LadderRow;
  /** 0-based: a root row (no present parent) is depth 0. */
  depth: number;
  children: LadderTreeNode[];
}

/**
 * Nest a realm's flat ladder rows (#3983 Task 8 decision 2): a row whose
 * `parent_title_id` isn't present among the rows is a root. Children keep
 * the API's own row order (already ancestry-depth-then-name ordered,
 * `almanach_reads.ladder_for_realm`), so no re-sort here.
 */
export function buildLadderTree(rows: LadderRow[]): LadderTreeNode[] {
  const byId = new Map<number, LadderTreeNode>();
  for (const row of rows) {
    byId.set(row.title_id, { row, depth: 0, children: [] });
  }
  const roots: LadderTreeNode[] = [];
  for (const row of rows) {
    const node = byId.get(row.title_id);
    if (!node) continue;
    const parent = row.parent_title_id != null ? byId.get(row.parent_title_id) : undefined;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }
  const setDepth = (nodes: LadderTreeNode[], depth: number) => {
    for (const node of nodes) {
      node.depth = depth;
      setDepth(node.children, depth + 1);
    }
  };
  setDepth(roots, 0);
  return roots;
}

/**
 * The level bar's tier set (#3983 Task 8 review fix round 1): the distinct
 * tiers actually present among the rows (`displayTier`-mapped, so a march
 * row contributes "county" rather than a separate "march" entry), in
 * `TIER_ORDER`. No synthesized "one tier above" entry — a tier with no rows
 * at all (e.g. the realm's own crown when it isn't itself a `Title` row)
 * simply doesn't get a button. Empty when there are no rows.
 */
export function levelBarTiers(rows: LadderRow[]): Tier[] {
  const present = new Set<Tier>();
  for (const row of rows) {
    const index = tierIndex(displayTier(row.tier));
    if (index !== -1) present.add(TIER_ORDER[index]);
  }
  return TIER_ORDER.filter((tier) => present.has(tier));
}

/**
 * The tier that opens by default (#3983 Task 8 decision 3): the shallowest
 * `displayTier`-mapped tier among the rows themselves.
 */
export function defaultPressedTier(rows: LadderRow[]): Tier | null {
  const indices = rows
    .map((row) => tierIndex(displayTier(row.tier)))
    .filter((index) => index !== -1);
  if (indices.length === 0) return null;
  return TIER_ORDER[Math.min(...indices)];
}

/**
 * Whether a rung at `tier` defaults open under `pressedTier` (decision 3):
 * at or above the pressed tier expands, below it collapses, both compared
 * through `displayTier` so a march row expands exactly like a county row.
 * Unknown tiers default open rather than hide data the level bar doesn't
 * know about.
 */
export function defaultExpanded(tier: string, pressedTier: string | null): boolean {
  if (pressedTier == null) return true;
  const tierIdx = tierIndex(displayTier(tier));
  const pressedIdx = tierIndex(displayTier(pressedTier));
  if (tierIdx === -1 || pressedIdx === -1) return true;
  return tierIdx <= pressedIdx;
}

/** The read-only "under" context a dialog shows for its parent rung. */
export interface LadderParentRef {
  title_id: number;
  name: string;
  tier: string;
}
