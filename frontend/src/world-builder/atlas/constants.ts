/**
 * Shared Atlas constants (#3477 fix round 1) — hoisted out of `AtlasPage`,
 * `AreaPage`, and `IndexRail`, which each independently declared the same
 * `BUILDING_LEVEL` constant and the same "does this area hold child areas or
 * rooms directly" kind ternary.
 */
import { AREA_LEVELS } from '../types';
import type { AtlasViewKind } from './useAtlasState';

/** Mirrors `world.areas.constants.AreaLevel.BUILDING` (see `../types.ts`'s `AREA_LEVELS`). */
export const BUILDING_LEVEL = 10;

/**
 * A BUILDING-level area holds rooms directly — its Atlas view is the room
 * grid (`'roomgrid'`, Task 5's `<Lattice mode="rooms"/>`). Anything above
 * BUILDING can hold child areas of its own (`'area'`, `<Lattice
 * mode="areas"/>`) — see `AreaPage`'s ledger-vs-lattice-only split.
 */
export function areaViewKind(level: number): AtlasViewKind {
  return level === BUILDING_LEVEL ? 'roomgrid' : 'area';
}

const ORDERED_LEVELS = AREA_LEVELS.map((choice) => choice.value).sort((a, b) => a - b);

/**
 * The level a plotted square realizes into on an `'areas'`-mode `<Lattice/>`
 * (Task 5) — one step down the `AreaLevel` ladder from `level`, e.g. a Ward
 * (30) plots Neighborhoods/Buildings (whichever sits directly below it,
 * currently Neighborhood at 20). Never called for a BUILDING area itself
 * (its Lattice is `'rooms'` mode, which realizes rooms, not child areas).
 */
export function childLevelOf(level: number): number {
  const index = ORDERED_LEVELS.indexOf(level);
  if (index <= 0) return BUILDING_LEVEL;
  return ORDERED_LEVELS[index - 1];
}

/** The shape `insertableLevels` reads: an area entry with its level, or a room entry. */
export interface LadderNode {
  level?: number;
  kind?: 'area' | 'room';
}

/**
 * The area levels that fit strictly between `upper` and `lower`, highest
 * first (the `FolioCrumb` insert point, 2026-09-09). A room sits at any level,
 * so anything below `upper` down to BUILDING fits above it; an area only
 * admits the levels between the two.
 */
export function insertableLevels(
  upper: LadderNode,
  lower: LadderNode
): { value: number; label: string }[] {
  if (upper.level == null) return [];
  const floor = lower.kind === 'room' ? BUILDING_LEVEL : (lower.level ?? BUILDING_LEVEL) + 1;
  const ceiling = upper.level;
  return AREA_LEVELS.filter((choice) => choice.value < ceiling && choice.value >= floor).sort(
    (a, b) => b.value - a.value
  );
}
