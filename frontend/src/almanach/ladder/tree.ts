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

/** Mirrors `TitleTier`'s display labels. */
export const TIER_LABELS: Record<string, string> = {
  empire: 'Empire',
  kingdom: 'Kingdom',
  duchy: 'Duchy',
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
 * The level bar's tier set (#3983 Task 8): contiguous from one tier above
 * the shallowest row tier (the realm's own held crown — it never appears as
 * a row itself) down through the deepest row tier present. Empty when there
 * are no rows.
 */
export function levelBarTiers(rows: LadderRow[]): Tier[] {
  const indices = rows.map((row) => tierIndex(row.tier)).filter((index) => index !== -1);
  if (indices.length === 0) return [];
  const minIndex = Math.min(...indices);
  const maxIndex = Math.max(...indices);
  const start = Math.max(0, minIndex - 1);
  return TIER_ORDER.slice(start, maxIndex + 1);
}

/**
 * The tier that opens by default (#3983 Task 8 decision 3): the shallowest
 * tier among the rows themselves — never the implicit crown tier above them,
 * since nothing would be visible yet if that were pressed.
 */
export function defaultPressedTier(rows: LadderRow[]): Tier | null {
  const indices = rows.map((row) => tierIndex(row.tier)).filter((index) => index !== -1);
  if (indices.length === 0) return null;
  return TIER_ORDER[Math.min(...indices)];
}

/**
 * Whether a rung at `tier` defaults open under `pressedTier` (decision 3):
 * at or above the pressed tier expands, below it collapses. Unknown tiers
 * default open rather than hide data the level bar doesn't know about.
 */
export function defaultExpanded(tier: string, pressedTier: string | null): boolean {
  if (pressedTier == null) return true;
  const tierIdx = tierIndex(tier);
  const pressedIdx = tierIndex(pressedTier);
  if (tierIdx === -1 || pressedIdx === -1) return true;
  return tierIdx <= pressedIdx;
}

/** The read-only "under" context a dialog shows for its parent rung. */
export interface LadderParentRef {
  title_id: number;
  name: string;
  tier: string;
}
